import hashlib
import os
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


# --- Plan 12.2 READ: the reserved runtime tree `.optimus/` on the planner's ranged read ------------------------


def _runtime_sentinel(tmp_path) -> Path:
    sentinel = tmp_path / ".optimus" / "telemetry.ndjson"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("RUNTIME-SENTINEL-7f3a", encoding="utf-8")
    return sentinel


@pytest.fixture
def directory_alias():
    """Make directory aliases: a Windows junction where `_winapi` exists, else a directory symlink. Each alias itself is
    removed at teardown, never anything through it."""
    made: list[tuple[Path, bool]] = []

    def make(link: Path, target: Path) -> None:
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            import _winapi
        except ImportError:
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                pytest.skip(f"directory alias unavailable: {exc}")
            made.append((link, False))
            return
        _winapi.CreateJunction(str(target), str(link))
        made.append((link, True))

    yield make
    for link, junction in reversed(made):
        os.rmdir(link) if junction else link.unlink()


def test_read_file_range_blocks_the_runtime_tree_before_reading(tmp_path, monkeypatch):
    _runtime_sentinel(tmp_path)
    tools = executor(tmp_path)
    opened: list[Path] = []
    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: opened.append(self) or original_read_bytes(self))

    with pytest.raises(LoopToolBlocked) as exc:
        _read_range(tools, tmp_path, path=".optimus/telemetry.ndjson", start_byte=0, end_byte=7)

    assert exc.value.result.rule_id == "path.runtime.read"
    assert opened == []


def test_read_file_range_blocks_a_reserved_alias_into_ordinary_source_by_its_requested_name(tmp_path, directory_alias):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_text("print('ordinary')\n", encoding="utf-8")
    directory_alias(tmp_path / "a" / ".optimus", source)
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        _read_range(tools, tmp_path, path="a/.optimus/a.py", start_byte=0, end_byte=5)

    assert exc.value.result.rule_id == "path.runtime.read"


def test_read_file_range_blocks_an_ordinary_alias_into_the_runtime_tree(tmp_path, directory_alias):
    _runtime_sentinel(tmp_path)
    directory_alias(tmp_path / "src" / "rt", tmp_path / ".optimus")
    tools = executor(tmp_path)

    with pytest.raises(LoopToolBlocked) as exc:
        _read_range(tools, tmp_path, path="src/rt/telemetry.ndjson", start_byte=0, end_byte=7)

    assert exc.value.result.rule_id == "path.runtime.read"


def test_read_file_range_blocks_an_ordinary_file_symlink_into_the_runtime_tree(tmp_path, monkeypatch):
    sentinel = _runtime_sentinel(tmp_path)
    link = tmp_path / "src" / "link.ndjson"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(sentinel)  # READ v3 §6 A5: a file symlink, on POSIX or Windows with the privilege
    except OSError as exc:
        pytest.skip(f"file symlink unavailable: {exc}")
    tools = executor(tmp_path)
    opened: list[Path] = []
    original_read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", lambda self: opened.append(self) or original_read_bytes(self))

    with pytest.raises(LoopToolBlocked) as exc:
        _read_range(tools, tmp_path, path="src/link.ndjson", start_byte=0, end_byte=7)

    assert exc.value.result.rule_id == "path.runtime.read"
    assert opened == []


def test_read_file_range_denies_an_unresolvable_target_through_the_guard(tmp_path, monkeypatch):
    target = tmp_path / "src" / "unresolvable.py"
    target.parent.mkdir(parents=True)
    target.write_text("print('x')\n", encoding="utf-8")
    original_resolve = Path.resolve

    def failing_resolve(self, strict=False):
        if self.name == "unresolvable.py":
            raise OSError("simulated resolution failure")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(Path, "resolve", failing_resolve)
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=("gateway.optimus.ai",))
    tools = GuardedLoopToolExecutor(guard=guard)

    with pytest.raises(LoopToolBlocked) as exc:
        _read_range(tools, tmp_path, path="src/unresolvable.py", start_byte=0, end_byte=5)

    assert exc.value.result.rule_id == "path.unresolved.read"
    assert guard.audit_events()[-1].verdict == "BLOCK"


def test_read_file_range_still_reads_ordinary_source_through_a_normal_alias(tmp_path, directory_alias):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_bytes(b"hello")
    directory_alias(tmp_path / "lib", source)

    evidence = _read_range(executor(tmp_path), tmp_path, path="lib/a.py", start_byte=0, end_byte=5)

    assert evidence.range_text == "hello"
