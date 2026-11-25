"""#589: a guard that refuses a step of an approved plan ends the turn normally. The person approved the plan; the guard
then refused its WRITE (or the read before it, or an EDIT) or a TEST. The refusal used to leave the prompt handler as an
exception. Now the turn ends with a fixed text that names neither the refused path nor the command (#583), the
conversation outcome is FAILED, nothing is written or run after the refusal, and the cause is in the debug trace.

Driven through the real AcpDuplexAdapter and the real AgentRunner; only the gateway and the shell are doubles. Every
non-ASCII character and every backslash is built with chr()."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from optimus.acp import debug_trace
from optimus.acp.conversation import ConversationOutcome
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore
from optimus.agent.models import GUARD_REFUSAL_TEXTS, TEST_GUARD_REFUSED, WRITE_GUARD_REFUSED
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc
from tests.unit.agent.test_directive_path_characters import _SamePlan, _strings

BS = chr(92)
NIHONGO = chr(0x65E5) + chr(0x672C) + chr(0x8A9E)
WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="the guard refuses this path only under Windows path rules")


class _Runner:
    """The real AgentRunner; TEST commands go to ``shell`` (recording by default), never a process."""

    def __init__(self, gateway: _SamePlan, shell: Any = None) -> None:
        self.commands: list[list[str]] = []
        self._shell_impl = shell
        self._runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore(), shell_runner=self._shell)

    def _shell(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        if self._shell_impl is not None:
            return self._shell_impl(command)
        return CompletedProcess(command, 0, "", "")

    def run(self, request, **kwargs):
        return self._runner.run(request, **kwargs)


async def _drive(tmp_path: Path, plan: str, *, shell: Any = None, before_approve: Any = None):
    runner = _Runner(_SamePlan(plan), shell)
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound
    )
    new = {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    session_id = (await _rpc(adapter, new))["result"]["sessionId"]
    prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change small.py"}]}
    task = asyncio.create_task(_rpc(adapter, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": prompt}))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=10)
    if before_approve is not None:
        before_approve()
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    response = await asyncio.wait_for(task, timeout=10)
    records = adapter._sessions.get(session_id).conversation.records
    return response, outbound, runner, records


def _files(root: Path) -> dict[str, bytes]:
    """Every workspace file outside the runtime tree, with its bytes."""
    return {
        p.relative_to(root).as_posix(): p.read_bytes()
        for p in root.rglob("*")
        if p.is_file() and ".optimus" not in p.relative_to(root).parts
    }


def _final_text(outbound) -> str:
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    return [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]


def _assert_ended_normally(response, outbound, runner, records, *, code: str, token: str) -> None:
    assert "result" in response, response
    result = response["result"]
    assert result["stopReason"] == "end_turn"
    assert result["_meta"]["runStopReason"] == code, (result, _final_text(outbound), runner.commands)
    [record] = records.values()
    assert record.outcome is ConversationOutcome.FAILED
    final = _final_text(outbound)
    assert final.strip() == GUARD_REFUSAL_TEXTS[code]
    assert token not in final and token not in record.completion_text
    assert runner.commands == []  # no TEST ran after the refusal
    # No completed-plan update claims the refused work was done.
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    assert not [u for u in updates if u["sessionUpdate"] == "plan" and any(e.get("status") == "completed" for e in u.get("entries", []))]


# (plan path, a secret file that already exists or None). The secret rule judges the resolved target, and Windows
# resolves "id_rsa." to the secret's own name only when it exists (see the #589 report). The issue's drive, rooted and
# alternate-data-stream rows never reach the guard since #590: test_directive_path_characters.py pins their
# parse-time rejection.
WRITE_ROWS = {
    "runtime-tree-posix-separator": pytest.param(".optimus/state.txt", None),
    "runtime-tree": pytest.param(f".optimus{BS}state.txt", None, marks=WINDOWS_ONLY),
    "secret-id_rsa-trailing-dot": pytest.param("id_rsa.", "id_rsa", marks=WINDOWS_ONLY),
    "secret-env-trailing-dot": pytest.param(".env.", None),  # the lexical ".env." rule, on every platform
}


@pytest.mark.parametrize(("path", "secret"), WRITE_ROWS.values(), ids=WRITE_ROWS)
async def test_a_guard_refused_write_ends_the_turn_with_fixed_text(path, secret, tmp_path):
    (tmp_path / "small.py").write_text("old\n")
    if secret is not None:
        (tmp_path / secret).write_text("KEY=value\n")
    before = _files(tmp_path)

    response, outbound, runner, records = await _drive(tmp_path, f"WRITE {path}\nnew\nTEST pytest -q\n")

    _assert_ended_normally(response, outbound, runner, records, code=WRITE_GUARD_REFUSED, token=path)
    assert _files(tmp_path) == before
    assert not (tmp_path / ".optimus" / "state.txt").exists()


async def test_a_guard_refused_read_before_write_ends_the_turn_with_fixed_text(tmp_path):
    """The WRITE target exists, so the WRITE first reads it; the secret rule refuses that read."""
    (tmp_path / ".env").write_text("KEY=value\n")
    before = _files(tmp_path)

    response, outbound, runner, records = await _drive(tmp_path, "WRITE .env\nnew\nTEST pytest -q\n")

    _assert_ended_normally(response, outbound, runner, records, code=WRITE_GUARD_REFUSED, token=".env")
    assert _files(tmp_path) == before


async def test_a_guard_refused_edit_ends_the_turn_with_fixed_text(tmp_path):
    """Between approval being asked and given, small.py becomes a link to a file outside the workspace with the same
    bytes: the EDIT's base still matches, and the guard refuses the read of the resolved target."""
    (tmp_path / "ws").mkdir()
    workspace = tmp_path / "ws"
    (workspace / "small.py").write_text("old\n")
    outside = tmp_path / "outside.py"
    outside.write_text("old\n")
    try:
        os.symlink(outside, tmp_path / "probe-link")
    except OSError:
        pytest.skip("this host cannot create symbolic links")

    def swap() -> None:
        (workspace / "small.py").unlink()
        os.symlink(outside, workspace / "small.py")

    plan = "EDIT small.py\n<<<<<<< OLD\nold\n======= NEW\nnew\n>>>>>>> END\nTEST pytest -q\n"
    response, outbound, runner, records = await _drive(workspace, plan, before_approve=swap)

    _assert_ended_normally(response, outbound, runner, records, code=WRITE_GUARD_REFUSED, token="small.py")
    assert outside.read_text() == "old\n"


async def test_a_guard_refused_test_ends_the_turn_with_fixed_text(tmp_path):
    (tmp_path / "small.py").write_text("old\n")
    before = _files(tmp_path)
    token = f"tests/{NIHONGO}.py"

    response, outbound, runner, records = await _drive(tmp_path, f"TEST pytest {token}\nTEST pytest -q\n")

    _assert_ended_normally(response, outbound, runner, records, code=TEST_GUARD_REFUSED, token=NIHONGO)
    assert _files(tmp_path) == before


async def test_a_guard_refused_test_after_an_applied_write_keeps_the_write(tmp_path):
    (tmp_path / "small.py").write_text("old\n")

    response, outbound, runner, records = await _drive(tmp_path, f"WRITE small.py\nnew\nTEST pytest tests/{NIHONGO}.py\nTEST pytest -q\n")

    _assert_ended_normally(response, outbound, runner, records, code=TEST_GUARD_REFUSED, token=NIHONGO)
    assert (tmp_path / "small.py").read_text() == "new\n"


async def test_the_refusal_cause_is_in_the_debug_trace_without_the_path(tmp_path, monkeypatch):
    logged: list[dict[str, Any]] = []

    def record(*, location, data=None, **_):
        if location == "runner.py:guard_refusal":
            logged.append(data())
        return True

    monkeypatch.setattr(debug_trace, "acp_debug_log", record)  # the runner imports it at call time
    (tmp_path / "small.py").write_text("old\n")

    await _drive(tmp_path, f"TEST pytest tests/{NIHONGO}.py\n")
    await _drive(tmp_path, "WRITE .optimus/state.txt\nnew\n")

    assert logged == [
        {"directive": "TEST", "error_type": "MutationForbidden", "cause_type": None, "reason": "Unicode confusable detected"},
        {"directive": "WRITE", "error_type": "GuardDenied", "cause_type": "MutationForbidden", "reason": "runtime tree writes are denied"},
    ]
    assert not [s for s in _strings(logged) if NIHONGO in s or "state.txt" in s]


async def test_a_failure_that_is_not_a_guard_refusal_still_propagates(tmp_path):
    (tmp_path / "small.py").write_text("old\n")

    def broken(command: list[str]) -> CompletedProcess[str]:
        raise RuntimeError("the test runner broke")

    with pytest.raises(RuntimeError, match="the test runner broke"):
        await _drive(tmp_path, "TEST pytest -q\n", shell=broken)


def test_the_fixed_texts_name_no_path_or_command_and_stay_short():
    for text in GUARD_REFUSAL_TEXTS.values():
        assert "safety check" in text and len(text) < 200
