"""#700: an expected filesystem or launch failure at a directive boundary ends the turn with a stated stop, never an exception
out of the adapter. Every case goes through `session/prompt` on the real adapter and the real runner: a READ of a file that is
not UTF-8, a TEST that cannot be launched, and an EDIT whose read or write fails. A change already applied stays applied and is
reported."""

from __future__ import annotations

import subprocess

import pytest

from optimus.acp.settlement import EffectState
from optimus.acp.spec import _shown
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from tests.unit.agent import test_directive_path_characters as drive_module
from tests.unit.agent.test_directive_path_characters import _drive, _RealRunner, _SamePlan, _strings
from tests.unit.agent.test_write_new_folders import NOT_APPLIED, _final_text

NOT_UTF8 = bytes([0x63, 0x61, 0x66, 0xE9, 0x0A, 0xFF, 0x00])  # Latin-1 text and stray bytes: not UTF-8


def _effect(records) -> EffectState:
    [record] = records.values()
    return record.effect_state


async def test_a_read_of_the_write_target_that_is_not_utf8_stops_with_a_reason_and_leaves_its_bytes(tmp_path):
    (tmp_path / "legacy.txt").write_bytes(NOT_UTF8)
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan("READ legacy.txt\nWRITE legacy.txt\nnew\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "legacy.txt").read_bytes() == NOT_UTF8
    assert runner.commands == []  # the plan's TESTs check a change that was not made
    assert _final_text(outbound).startswith(NOT_APPLIED)
    assert _effect(records) is EffectState.NONE


async def test_a_read_of_another_file_that_is_not_utf8_is_skipped_and_the_plan_still_runs(tmp_path):
    # As a READ that cannot be opened already is: the plan's WRITE was computed at planning time and does not use the read.
    (tmp_path / "legacy.txt").write_bytes(NOT_UTF8)
    result, _outbound, runner, records = await _drive(tmp_path, _SamePlan("READ legacy.txt\nWRITE out.py\nX = 1\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] is None and result["stopReason"] == "end_turn"
    assert (tmp_path / "out.py").read_bytes() == b"X = 1\n"
    assert runner.commands == [["pytest", "-q"]]
    assert (tmp_path / "legacy.txt").read_bytes() == NOT_UTF8
    assert _effect(records) is EffectState.COMPLETE


class _LaunchingRunner(_RealRunner):
    """The real runner with no shell double: TESTs go through the real bounded launcher, whose Popen the test replaces."""

    def __init__(self, gateway) -> None:
        super().__init__(gateway)
        self._runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore())


async def test_a_test_that_cannot_be_launched_stops_with_a_reason_and_keeps_the_applied_write(tmp_path, monkeypatch):
    launches: list[list[str]] = []

    def missing(args, *pargs, **kwargs):
        launches.append(list(args))
        raise FileNotFoundError(2, "No such file or directory")  # pytest is not on PATH

    from optimus.acp import debug_trace

    logged: list[dict] = []
    monkeypatch.setattr(debug_trace, "acp_debug_log", lambda **kwargs: logged.append({**kwargs, "data": kwargs["data"]()}))
    monkeypatch.setattr(drive_module, "_RealRunner", _LaunchingRunner)
    monkeypatch.setattr(subprocess, "Popen", missing)
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan("WRITE a.py\nA = 1\nTEST pytest -q\nTEST pytest -q tests\n"))

    assert result["_meta"]["runStopReason"] == "TEST_NOT_STARTED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "a.py").read_bytes() == b"A = 1\n"  # the WRITE that succeeded is kept
    assert launches == [["pytest", "-q"]]  # the later TEST was not tried
    tool_calls = [n["params"]["update"] for n in outbound.notifications if n["params"].get("update", {}).get("sessionUpdate") == "tool_call"]
    assert any(_shown("did not start pytest -q") in text for text in _strings(tool_calls))  # Codex r1 L9: not "ran"
    final = _final_text(outbound)
    assert "could not be started" in final and "Applied:" + chr(10) + "- " + _shown("wrote a.py") in final  # escaped as #688 does
    assert _effect(records) is EffectState.PARTIAL  # the WRITE happened; neither TEST ran
    [cause] = [entry["data"] for entry in logged if entry.get("hypothesis_id") == "P700-TEST"]
    assert cause == {"step": "launch", "program": "pytest", "error_type": "FileNotFoundError", "errno": 2, "winerror": None}


async def test_a_test_that_fails_while_running_stops_unconfirmed_and_keeps_the_applied_write(tmp_path, monkeypatch):
    seen: list[list[str]] = []

    def broken_pipe(self, command):
        seen.append(command)
        raise BrokenPipeError(32, "Broken pipe")  # the process started; its pipes failed

    monkeypatch.setattr(_RealRunner, "_shell", broken_pipe)
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan("WRITE a.py\nA = 1\nTEST pytest -q\nTEST pytest -q tests\n"))

    assert result["_meta"]["runStopReason"] == "TEST_STOP_UNCONFIRMED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "a.py").read_bytes() == b"A = 1\n"
    assert seen == [["pytest", "-q"]]
    final = _final_text(outbound)
    assert "may still be running" in final and "Applied:" + chr(10) + "- " + _shown("wrote a.py") in final  # escaped as #688 does
    assert _effect(records) is EffectState.INDETERMINATE  # it ran, and nothing confirmed what it did


async def test_an_edit_whose_read_fails_stops_with_a_reason(tmp_path, monkeypatch):
    from optimus.agent.tools import AgentToolbox

    (tmp_path / "small.py").write_text("a = 1\n")
    real = AgentToolbox.read_file

    def locked_on_replay(self, path, **kwargs):
        if kwargs.get("newline") == "" and self._context.approval_granted:  # the EDIT's raw read, after approval
            raise PermissionError(13, "locked by another process")
        return real(self, path, **kwargs)

    monkeypatch.setattr(AgentToolbox, "read_file", locked_on_replay)
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\nTEST pytest -q\n"
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan(plan))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and result["stopReason"] == "end_turn"
    assert (tmp_path / "small.py").read_text() == "a = 1\n"
    assert runner.commands == []
    assert _final_text(outbound).startswith(NOT_APPLIED)
    assert _effect(records) is EffectState.NONE


async def test_an_edit_whose_write_fails_stops_with_a_reason(tmp_path, monkeypatch):
    (tmp_path / "small.py").write_text("a = 1\n")

    def disk_full(descriptor):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("os.fsync", disk_full)
    plan = "EDIT small.py\n<<<<<<< OLD\na = 1\n======= NEW\na = 2\n>>>>>>> END\nTEST pytest -q\n"
    result, outbound, runner, records = await _drive(tmp_path, _SamePlan(plan))

    assert result["_meta"]["runStopReason"] == "WRITE_DIRECTIVE_NOT_EXECUTED" and result["stopReason"] == "end_turn"
    assert runner.commands == []
    assert _final_text(outbound).startswith(NOT_APPLIED)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["small.py"] and (tmp_path / "small.py").read_text() == "a = 1\n"
    assert _effect(records) is EffectState.NONE  # #691: the staged write left nothing behind


@pytest.mark.parametrize("plan", ["READ legacy.txt\nExplain it.\n"], ids=["planning-read"])
def test_a_planning_read_of_a_file_that_is_not_utf8_does_not_raise(plan, tmp_path):
    from optimus.agent.models import AgentRunRequest, ExecutionMode

    (tmp_path / "legacy.txt").write_bytes(NOT_UTF8)
    runner = AgentRunner(gateway_client=_SamePlan(plan), model="glm-5.2", state_store=InMemoryAgentStateStore())

    result = runner.run(AgentRunRequest(run_id="r", task="Explain it", execution_mode=ExecutionMode.PLAN, workspace_root=tmp_path))

    assert result.final_state == "CHAT_ONLY"


async def test_a_markdown_shaped_name_in_a_test_stop_is_shown_inert_and_kept_raw(tmp_path, monkeypatch):
    # Codex r1: the applied WRITE listed by a TEST stop is escaped where it is shown (#688); the history keeps it raw
    from tests.unit.acp.test_markdown_path_display import TOKENS, _live

    def missing(args, *pargs, **kwargs):
        raise FileNotFoundError(2, "No such file or directory")

    name = TOKENS["bare-address"] + "/a.py"
    monkeypatch.setattr(drive_module, "_RealRunner", _LaunchingRunner)
    monkeypatch.setattr(subprocess, "Popen", missing)
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan(f"WRITE {name}\nA = 1\nTEST pytest -q\n"))

    assert result["_meta"]["runStopReason"] == "TEST_NOT_STARTED"
    final = _final_text(outbound)
    assert _shown(f"wrote {name}") in final and _live(final) == []
    [record] = records.values()
    assert f"wrote {name}" in record.completion_text
