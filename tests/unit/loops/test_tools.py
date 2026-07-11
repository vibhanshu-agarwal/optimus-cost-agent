import hashlib
from pathlib import Path

import pytest

from optimus.agent.planning_loop import (
    PlanningReadError,
    PlanningReadEvidence,
    PlanningReadRequest,
    verify_planning_source_hash,
)
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode, GenerationScope


def executor(tmp_path) -> GuardedLoopToolExecutor:
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    return GuardedLoopToolExecutor(guard=guard)


def _read_range(
    tools: GuardedLoopToolExecutor,
    tmp_path,
    *,
    path: str,
    start_byte: int,
    end_byte: int,
) -> PlanningReadEvidence:
    return tools.read_file_range(
        workspace_root=tmp_path,
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.PLAN,
        request=PlanningReadRequest(path=path, start_byte=start_byte, end_byte=end_byte),
    )


def test_loop_tool_executor_blocks_plan_mode_shell(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.PLAN,
            tool_surface=ToolSurface.SHELL,
            action="pytest tests/unit -q",
            command=("pytest", "tests/unit", "-q"),
            approval_granted=True,
        )

    assert exc.value.result.verdict is PreToolVerdict.BLOCK
    assert exc.value.result.rule_id == "mode.plan_chat.no_shell"


def test_loop_tool_executor_allows_agent_mode_safe_pytest(tmp_path):
    tools = executor(tmp_path)

    result = tools.preflight(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.SHELL,
        action="pytest tests/unit -q",
        command=("pytest", "tests/unit", "-q"),
        approval_granted=True,
    )

    assert result.verdict is PreToolVerdict.ALLOW


def test_loop_tool_executor_preserves_multi_file_approval_hold(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        tools.preflight(
            run_id="run-1",
            session_id="session-1",
            execution_mode=ExecutionMode.AGENT,
            tool_surface=ToolSurface.FILE_WRITE,
            action="write",
            target_path=str(tmp_path / "src" / "optimus" / "x.py"),
            generation_scope=GenerationScope.MULTI_FILE_CHANGESET,
            approval_granted=False,
        )

    assert exc.value.result.verdict is PreToolVerdict.HOLD
    assert exc.value.result.requires_human_approval is True


def test_read_file_range_returns_exact_bytes_and_source_hash(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir(parents=True)
    content = "alpha\nbeta\n"
    target.write_bytes(content.encode("utf-8"))
    tools = executor(tmp_path)

    evidence = _read_range(tools, tmp_path, path="src/example.py", start_byte=0, end_byte=5)

    assert evidence.path == "src/example.py"
    assert evidence.range_text == "alpha"
    assert evidence.source_sha256 == hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_read_file_range_rejects_utf8_boundary_split(tmp_path):
    target = tmp_path / "src" / "utf8.py"
    target.parent.mkdir(parents=True)
    target.write_bytes("héllo".encode("utf-8"))
    tools = executor(tmp_path)

    with pytest.raises(PlanningReadError) as exc:
        _read_range(tools, tmp_path, path="src/utf8.py", start_byte=1, end_byte=2)
    assert exc.value.code == "PLANNING_READ_NOT_UTF8_ALIGNED"


def test_read_file_range_blocks_path_traversal(tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked):
        _read_range(tools, tmp_path, path="../outside.txt", start_byte=0, end_byte=6)


def test_read_file_range_blocks_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unsupported on this platform")
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked):
        _read_range(tools, tmp_path, path="link.txt", start_byte=0, end_byte=6)


def test_read_file_range_raises_for_missing_file(tmp_path):
    tools = executor(tmp_path)

    with pytest.raises(PlanningReadError) as exc:
        _read_range(tools, tmp_path, path="src/missing.py", start_byte=0, end_byte=4)
    assert exc.value.code == "PLANNING_READ_FILE_NOT_FOUND"


def test_verify_planning_source_hash_detects_changed_file(tmp_path):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_text("version-1", encoding="utf-8")
    tools = executor(tmp_path)
    evidence = _read_range(tools, tmp_path, path="src/example.py", start_byte=0, end_byte=9)

    target.write_text("version-2", encoding="utf-8")

    with pytest.raises(PlanningReadError) as exc:
        verify_planning_source_hash(
            workspace_root=tmp_path,
            path=evidence.path,
            expected_sha256=evidence.source_sha256,
        )
    assert exc.value.code == "PLANNING_READ_SOURCE_CHANGED"


def test_read_file_range_checks_guard_before_opening_file(tmp_path, monkeypatch):
    target = tmp_path / "src" / "example.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"hello")
    tools = executor(tmp_path)
    events: list[str] = []
    original_check = PreToolGuard.check
    original_read_bytes = Path.read_bytes

    def tracking_check(self, request: PreToolRequest):
        events.append("guard")
        return original_check(self, request)

    def tracking_read_bytes(self: Path):
        events.append("open")
        return original_read_bytes(self)

    monkeypatch.setattr(PreToolGuard, "check", tracking_check)
    monkeypatch.setattr(Path, "read_bytes", tracking_read_bytes)

    _read_range(tools, tmp_path, path="src/example.py", start_byte=0, end_byte=5)

    assert events.index("guard") < events.index("open")
