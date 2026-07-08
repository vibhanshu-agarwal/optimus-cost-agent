from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.e2e_transcript import PLAN_9_6_E2E_TRANSCRIPT_PATH, E2eAcpTranscriptWriter
from optimus.acp.preflight import PreflightFailure, run_preflight
from optimus.agent.directives import AgentDirectiveParseError, parse_agent_plan
from optimus.agent.state_store import RedisAgentStateStore
from optimus.redis.async_bridge import sync_await
from tests.e2e.acp.acp_subprocess_env import build_acp_subprocess_env
from tests.integration.optimus_gateway.gateway_env import project_root

pytestmark = pytest.mark.e2e

_WALL_CLOCK_TIMEOUT_SECONDS = 120
_DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")
_LIVE_MODEL = "claude-haiku"
_DOCSTRING_TASK = (
    "Add a module docstring to `example.py` describing its function. "
    "Modify only `example.py`; do not create any other files or tests."
)


def _live_max_cost_usd() -> Decimal:
    raw = os.environ.get("OPTIMUS_LIVE_MAX_COST_USD", "").strip()
    if not raw:
        return _DEFAULT_LIVE_MAX_COST_USD
    return Decimal(raw)


def _assert_cost_within_cap(cost_usd: Decimal) -> None:
    cap = _live_max_cost_usd()
    assert cost_usd <= cap, f"live e2e cost {cost_usd} exceeded OPTIMUS_LIVE_MAX_COST_USD cap {cap}"


def _directive_parse_outcome(plan_text: str) -> str:
    try:
        parse_agent_plan(plan_text)
    except AgentDirectiveParseError:
        return "UNPARSEABLE_PLAN"
    return "PARSED"


def _init_git_workspace(workspace: Path) -> None:
    completed = subprocess.run(
        ["git", "init"],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(f"git init failed in e2e workspace: {completed.stderr}")


def _plan_keys_for_run(client: object, run_id: str) -> set[str]:
    async def _collect() -> set[str]:
        keys: set[str] = set()
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            keys.add(key)
        return keys

    return sync_await(_collect())


def _delete_plan_keys(client: object, run_id: str) -> None:
    async def _delete() -> None:
        async for key in client.scan_iter(match=f"agent:plan:{run_id}*"):
            await client.delete(key)

    sync_await(_delete())


class _NdjsonSubprocessSession:
    def __init__(self, *, process: subprocess.Popen[str], transcript: E2eAcpTranscriptWriter) -> None:
        self._process = process
        self._transcript = transcript
        self._inbound: queue.Queue[dict | None] = queue.Queue()
        self._stderr_lines: list[str] = []
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def send(self, message: Mapping[str, object]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("subprocess stdin is not available")
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
        predicate,
        error_message: str,
    ) -> dict:
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

    def wait_for_response(self, request_id: str | int, *, deadline: float) -> dict:
        return self.wait_for(
            deadline=deadline,
            predicate=lambda message: message.get("id") == request_id and ("result" in message or "error" in message),
            error_message=f"timed out waiting for JSON-RPC response id={request_id!r}",
        )

    def wait_for_request(self, method: str, *, deadline: float) -> dict:
        return self.wait_for(
            deadline=deadline,
            predicate=lambda message: message.get("method") == method and "result" not in message and "error" not in message,
            error_message=f"timed out waiting for JSON-RPC request method={method!r}",
        )

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
        pytest.fail(
            f"{error_message}\n"
            f"ACP subprocess exited early (code={code_text}).\n"
            f"stderr:\n{self.stderr_text()}"
        )

    def _fail_timeout(self, error_message: str) -> None:
        pytest.fail(f"{error_message}\nstderr:\n{self.stderr_text()}")


def _latest_plan_text_from_transcript(transcript: E2eAcpTranscriptWriter) -> str:
    for line in reversed(transcript.lines):
        if line["direction"] != "inbound":
            continue
        message = line["message"]
        if message.get("method") != "session/update":
            continue
        update = message.get("params", {}).get("update", {})
        if update.get("sessionUpdate") != "plan":
            continue
        blocks = update.get("content", [])
        texts = [block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
        if texts:
            return "\n".join(texts)
    return ""


def _run_docstring_turn(
    *,
    session: _NdjsonSubprocessSession,
    session_id: str,
    prompt_request_id: int,
    deadline: float,
    redis_store: RedisAgentStateStore,
    transcript: E2eAcpTranscriptWriter,
) -> tuple[dict, str, str]:
    session.send(
        {
            "jsonrpc": "2.0",
            "id": prompt_request_id,
            "method": "session/prompt",
            "params": {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": _DOCSTRING_TASK}],
            },
        }
    )

    permission_request: dict | None = None
    prompt_response: dict | None = None
    while time.monotonic() < deadline:
        if session._process.poll() is not None:
            session._fail_subprocess_exited("ACP subprocess exited during session/prompt turn")
        try:
            message = session._inbound.get(timeout=0.2)
        except queue.Empty:
            continue
        if message is None:
            session._fail_subprocess_exited("ACP subprocess stdout closed during session/prompt turn")
        if message.get("method") == "session/request_permission":
            permission_request = message
            break
        if message.get("id") == prompt_request_id and ("result" in message or "error" in message):
            prompt_response = message
            break

    run_id = f"{session_id}:{prompt_request_id}"
    if permission_request is None:
        if prompt_response is None:
            prompt_response = session.wait_for_response(prompt_request_id, deadline=deadline)
        plan_text = _latest_plan_text_from_transcript(transcript)
        if _directive_parse_outcome(plan_text) == "UNPARSEABLE_PLAN":
            return prompt_response, run_id, "UNPARSEABLE_PLAN"
        pytest.fail(
            "session/prompt completed without permission and without an UNPARSEABLE_PLAN marker.\n"
            f"response={prompt_response!r}\nplan_text={plan_text!r}"
        )

    assert permission_request["params"]["sessionId"] == session_id
    plan_hash = permission_request["params"]["options"][0]["metadata"]["planHash"]
    run_id = permission_request["params"]["metadata"]["runId"]

    plan_keys = _plan_keys_for_run(redis_store.redis_client, run_id)
    assert plan_keys, f"expected Redis plan keys for run_id={run_id!r}, found none"
    assert all(key.startswith(f"agent:plan:{run_id}") for key in plan_keys)

    loaded = redis_store.load_plan(run_id=run_id, plan_hash=plan_hash)
    assert loaded.cost_usd > Decimal("0")
    _assert_cost_within_cap(loaded.cost_usd)

    session.send(
        {
            "jsonrpc": "2.0",
            "id": permission_request["id"],
            "result": {
                "outcome": {"outcome": "selected", "optionId": "approve"},
                "metadata": {"approvalId": f"e2e-approval-{uuid.uuid4().hex}", "planHash": plan_hash},
            },
        }
    )
    prompt_response = session.wait_for_response(prompt_request_id, deadline=deadline)
    return prompt_response, run_id, "PARSED"


def test_spawned_acp_agent_live_docstring_turn(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    _init_git_workspace(workspace)
    example = workspace / "example.py"
    example.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
    original_text = example.read_text(encoding="utf-8")

    try:
        run_preflight(os.environ, workspace_root=workspace, strict=True, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    redis_url = os.environ["OPTIMUS_REDIS_URL"].strip()
    redis_store = RedisAgentStateStore.from_url(redis_url)
    subprocess_env = build_acp_subprocess_env(operator_environ=os.environ, root=project_root())
    transcript = E2eAcpTranscriptWriter()
    deadline = time.monotonic() + _WALL_CLOCK_TIMEOUT_SECONDS
    run_ids: set[str] = set()
    process: subprocess.Popen[str] | None = None
    session: _NdjsonSubprocessSession | None = None

    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "optimus.acp", "--workspace-root", str(workspace), "--model", _LIVE_MODEL],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env,
            text=True,
            bufsize=1,
        )
        session = _NdjsonSubprocessSession(process=process, transcript=transcript)

        session.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": True,
                    },
                    "clientInfo": {"name": "e2e-live", "version": "1.0.0"},
                },
            }
        )
        initialize_response = session.wait_for_response(1, deadline=deadline)
        assert initialize_response["result"]["protocolVersion"] == 1

        session.send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "session/new",
                "params": {"cwd": str(workspace), "mcpServers": []},
            }
        )
        session_response = session.wait_for_response(2, deadline=deadline)
        session_id = session_response["result"]["sessionId"]

        prompt_response, run_id, outcome = _run_docstring_turn(
            session=session,
            session_id=session_id,
            prompt_request_id=3,
            deadline=deadline,
            redis_store=redis_store,
            transcript=transcript,
        )
        run_ids.add(run_id)

        if outcome == "UNPARSEABLE_PLAN":
            first_output = _latest_plan_text_from_transcript(transcript)
            retry_response, retry_run_id, retry_outcome = _run_docstring_turn(
                session=session,
                session_id=session_id,
                prompt_request_id=4,
                deadline=deadline,
                redis_store=redis_store,
                transcript=transcript,
            )
            run_ids.add(retry_run_id)
            if retry_outcome == "UNPARSEABLE_PLAN":
                transcript.write(PLAN_9_6_E2E_TRANSCRIPT_PATH)
                retry_output = _latest_plan_text_from_transcript(transcript)
                pytest.fail(
                    "Model returned UNPARSEABLE_PLAN after one retry.\n\n"
                    f"First output:\n{first_output}\n\n"
                    f"Retry output:\n{retry_output}"
                )
            prompt_response = retry_response
            run_id = retry_run_id

        assert prompt_response["result"]["stopReason"] == "end_turn", prompt_response
        updated_text = example.read_text(encoding="utf-8")
        assert updated_text != original_text, "example.py was not modified by the spawned agent"
        assert '"""' in updated_text or "'''" in updated_text, f"expected a docstring in example.py:\n{updated_text}"
        assert "def greet" in updated_text, f"expected original greet() to be preserved in example.py:\n{updated_text}"
        assert "return 'hello'" in updated_text, f"expected greet body to be preserved in example.py:\n{updated_text}"

        loaded = redis_store.latest_plan_for_run(run_id=run_id)
        assert loaded is not None
        assert loaded.cost_usd > Decimal("0")
        _assert_cost_within_cap(loaded.cost_usd)
    except Exception:
        transcript.write(PLAN_9_6_E2E_TRANSCRIPT_PATH)
        raise
    finally:
        if session is not None:
            session.close_stdin()
            session.terminate()
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        for tracked_run_id in run_ids:
            _delete_plan_keys(redis_store.redis_client, tracked_run_id)
        transcript.write(PLAN_9_6_E2E_TRANSCRIPT_PATH)
