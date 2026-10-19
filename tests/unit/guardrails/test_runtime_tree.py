"""Plan 12.2 READ + W: the shared reserved-runtime predicate and the request metadata that carries a model's requested
path and an unresolvable target to the guard. These exercise the candidate's new entry points, so they make no
baseline claim; the route-level controls in the runner, loop, path and command tests do."""

import sys
from pathlib import Path

import pytest

from optimus.agent import workspace_context
from optimus.agent.tools import AgentToolbox
from optimus.guardrails import runtime_tree
from optimus.guardrails.path_safety import PathSafetyValidator, ValidationVerdict
from optimus.guardrails.permissions import ToolSurface
from optimus.guardrails.pre_tool import PreToolGuard, PreToolRequest, PreToolVerdict
from optimus.runtime.modes import ExecutionMode, GenerationScope
from optimus.runtime.state import AgentState, RuntimeContext


def test_the_reserved_name_is_one_shared_rule_with_automatic_context():
    assert runtime_tree.RUNTIME_DIR_NAME == ".optimus"
    assert workspace_context.RUNTIME_DIR_NAME is runtime_tree.RUNTIME_DIR_NAME


@pytest.mark.skipif(sys.platform != "win32", reason="the casefolded compare is the Windows rule")
def test_the_component_compare_is_casefolded_on_windows():
    assert runtime_tree.has_runtime_component(("src", ".OPTIMUS", "x"))


@pytest.mark.skipif(sys.platform == "win32", reason="the exact compare is the POSIX rule")
def test_the_component_compare_is_exact_on_posix():
    assert not runtime_tree.has_runtime_component(("src", ".OPTIMUS", "x"))


def test_lookalike_components_are_not_reserved():
    for name in (".optimus-notes", "optimus", ".optimus.bak", "x.optimus"):
        assert not runtime_tree.has_runtime_component(("a", name, "b")), name


@pytest.mark.parametrize("error", [OSError("simulated"), RuntimeError("simulated loop")], ids=["oserror", "runtimeerror"])
def test_an_unresolvable_target_resolves_to_none(monkeypatch, tmp_path, error):
    def failing(self, strict=False):
        raise error

    monkeypatch.setattr(Path, "resolve", failing)

    assert runtime_tree.resolve_target(tmp_path / "x") is None


def test_a_target_is_counted_relative_to_the_root_inside_it_and_absolute_outside_it(tmp_path):
    root = (tmp_path / ".optimus" / "ws").resolve()
    root.mkdir(parents=True)

    assert not runtime_tree.target_reserved(root / "src" / "a.py", root)  # an ancestor named .optimus is not reserved
    assert runtime_tree.target_reserved(root / ".optimus" / "x", root)
    assert runtime_tree.target_reserved(tmp_path / "other" / ".optimus" / "x", root)


def test_the_requested_name_is_reserved_even_when_its_target_is_ordinary(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    result = validator.validate_read(tmp_path / "src" / "a.py", requested_relative_path="a/.optimus/a.py")
    write = validator.validate_write(tmp_path / "src" / "a.py", requested_relative_path="a/.optimus/a.py")

    assert (result.verdict, result.rule_id) == (ValidationVerdict.BLOCK, "path.runtime.read")
    assert (write.verdict, write.rule_id) == (ValidationVerdict.BLOCK, "path.runtime.write")


def test_an_unresolved_target_is_blocked_but_a_secret_keeps_its_rule(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    unresolved = validator.validate_read(tmp_path / "src" / "a.py", requested_relative_path="src/a.py", target_unresolved=True)
    secret = validator.validate_read(tmp_path / ".env", requested_relative_path=".env", target_unresolved=True)
    unresolved_write = validator.validate_write(tmp_path / "src" / "a.py", requested_relative_path="src/a.py", target_unresolved=True)

    assert (unresolved.verdict, unresolved.rule_id) == (ValidationVerdict.BLOCK, "path.unresolved.read")
    assert secret.rule_id == "path.secret.read"
    assert (unresolved_write.verdict, unresolved_write.rule_id) == (ValidationVerdict.BLOCK, "path.unresolved.write")


def test_an_ordinary_requested_path_is_allowed(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    assert validator.validate_read(tmp_path / "src" / "a.py", requested_relative_path="src/a.py").verdict is ValidationVerdict.ALLOW
    assert validator.validate_write(tmp_path / "src" / "a.py", requested_relative_path="src/a.py").verdict is ValidationVerdict.ALLOW


def _file_request(target: Path, **metadata) -> PreToolRequest:
    return PreToolRequest(
        run_id="run-1",
        session_id="session-1",
        execution_mode=ExecutionMode.AGENT,
        tool_surface=ToolSurface.FILE_READ,
        action="read_file",
        target_path=str(target),
        generation_scope=GenerationScope.INLINE_SNIPPET,
        **metadata,
    )


def test_the_guard_carries_the_metadata_to_the_validator_and_audits_the_denial(tmp_path):
    guard = PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=())

    lexical = guard.check(_file_request(tmp_path / "src" / "a.py", requested_relative_path="a/.optimus/a.py"))
    unresolved = guard.check(_file_request(tmp_path / "src" / "a.py", requested_relative_path="src/a.py", target_unresolved=True))

    assert (lexical.verdict, lexical.rule_id) == (PreToolVerdict.BLOCK, "path.runtime.read")
    assert (unresolved.verdict, unresolved.rule_id) == (PreToolVerdict.BLOCK, "path.unresolved.read")
    assert [event.verdict for event in guard.audit_events()] == ["BLOCK", "BLOCK"]


def test_a_request_without_metadata_keeps_its_defaults():
    request = PreToolRequest(run_id="r", session_id=None, execution_mode=ExecutionMode.AGENT, tool_surface=ToolSurface.SHELL, action="x")

    assert request.requested_relative_path is None and request.target_unresolved is False


def _toolbox(workspace: Path) -> AgentToolbox:
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT, state=AgentState.EXECUTING, approval_granted=True, user_approval_id="approval-1")
    return AgentToolbox.for_workspace(workspace_root=workspace, context=context, run_id="run-1")


def test_the_toolbox_denies_a_reserved_requested_name_and_still_reads_ordinary_source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("ordinary\n", encoding="utf-8")
    toolbox = _toolbox(tmp_path)

    with pytest.raises(PermissionError):
        toolbox.read_file(tmp_path / "src" / "a.py", requested="a/.optimus/a.py")
    with pytest.raises(PermissionError):
        toolbox.write_file(tmp_path / "src" / "a.py", "forged\n", requested="a/.optimus/a.py")

    text, call = toolbox.read_file(tmp_path / "src" / "a.py", requested="src/a.py")
    assert text == "ordinary\n" and call.summary == "read src/a.py"
    assert (tmp_path / "src" / "a.py").read_text(encoding="utf-8") == "ordinary\n"
