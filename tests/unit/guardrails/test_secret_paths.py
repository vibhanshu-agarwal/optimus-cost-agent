"""#385: one secret-path rule, shared by model-issued file access (the permission guard) and automatic workspace
context. Model reads run through the real toolbox and guard here; the packing controls are in test_workspace_context."""

import os
import sys
from pathlib import Path

import pytest

from optimus.agent.planning_loop import PlanningReadRequest
from optimus.agent.tools import AgentToolbox
from optimus.guardrails import path_safety, permissions, secret_paths
from optimus.guardrails.path_safety import PathSafetyValidator
from optimus.guardrails.pre_tool import PreToolGuard
from optimus.loops.tools import GuardedLoopToolExecutor, LoopToolBlocked
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import AgentState, RuntimeContext


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "config/.env.production",
        ".ENV.Local",
        "C:\\work\\app\\.env.staging",
        ".env/settings",
        "deploy/.pypirc",
        "home/.ssh/id_rsa",
        "certs/server.pem",
        "tls/private.KEY",
        "secrets/db.txt",
    ],
)
def test_secret_paths_are_recognised(path):
    assert secret_paths.is_secret_path(path)


@pytest.mark.parametrize("path", ["env.py", "src/environment.py", "docs/dotenv.md", "token.py", "app/.environment"])
def test_ordinary_paths_are_not_secret(path):
    assert not secret_paths.is_secret_path(path)


def test_both_guard_layers_use_the_shared_rule():
    assert not hasattr(permissions, "_looks_like_secret_path") and not hasattr(path_safety, "_is_secret_path")
    assert permissions.is_secret_path is path_safety.is_secret_path is secret_paths.is_secret_path


@pytest.mark.parametrize("relative", [".env.local", "config/.env.production"])
def test_path_safety_blocks_env_variants_for_reads_and_writes(tmp_path, relative):
    validator = PathSafetyValidator(workspace_root=tmp_path)

    assert validator.validate_read(tmp_path / relative).rule_id == "path.secret.read"
    assert validator.validate_write(tmp_path / relative).rule_id == "path.secret.write"


def test_a_target_inside_the_workspace_is_judged_by_its_relative_parts(tmp_path):
    root = tmp_path / "secrets" / "project"

    assert not secret_paths.target_secret(root / "src" / "app.py", root)
    assert secret_paths.target_secret(root / "config" / ".env.local", root)
    assert secret_paths.target_secret(tmp_path / "elsewhere" / ".env", root), "outside: judged by absolute parts"


def _toolbox(workspace: Path) -> AgentToolbox:
    context = RuntimeContext(execution_mode=ExecutionMode.AGENT, state=AgentState.EXECUTING, approval_granted=True, user_approval_id="approval-1")
    return AgentToolbox.for_workspace(workspace_root=workspace, context=context, run_id="run-1")


@pytest.mark.parametrize("relative", [".env.local", "config/.env.production"])
def test_a_model_read_of_an_env_variant_is_denied(tmp_path, relative):
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("DUMMY_PROOF_TOKEN=not-a-real-secret-0000\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    toolbox = _toolbox(tmp_path)

    with pytest.raises(PermissionError, match="secret"):
        toolbox.read_file(target, requested=relative)
    assert toolbox.read_file(tmp_path / "app.py", requested="app.py")[0] == "print('ok')\n"


def test_a_secret_requested_name_is_denied_even_when_its_target_is_ordinary(tmp_path):
    validator = PathSafetyValidator(workspace_root=tmp_path)
    ordinary = tmp_path / "config" / "db.txt"

    assert validator.validate_read(ordinary, requested_relative_path=".env.local/db.txt").rule_id == "path.secret.read"
    assert validator.validate_write(ordinary, requested_relative_path=".env.local/db.txt").rule_id == "path.secret.write"
    assert validator.validate_read(ordinary, requested_relative_path="config/db.txt").rule_id == "path.read.allowed"


@pytest.mark.skipif(sys.platform != "win32", reason="NTFS directory junctions are a Windows mechanism")
def test_a_secret_named_junction_is_denied_for_toolbox_and_ranged_reads(tmp_path):
    import _winapi  # CreateJunction needs no privilege, unlike a symlink

    config = tmp_path / "config"
    config.mkdir()
    (config / "db.txt").write_text("ordinary\n", encoding="utf-8")
    alias = tmp_path / ".env.local"
    _winapi.CreateJunction(str(config), str(alias))
    try:
        toolbox = _toolbox(tmp_path)
        with pytest.raises(PermissionError, match="secret"):
            toolbox.read_file(alias / "db.txt", requested=".env.local/db.txt")
        assert toolbox.read_file(config / "db.txt", requested="config/db.txt")[0] == "ordinary\n"

        tools = GuardedLoopToolExecutor(guard=PreToolGuard.for_workspace(workspace_root=tmp_path, allowed_network_hosts=()))

        def read(path: str):
            return tools.read_file_range(
                workspace_root=tmp_path,
                run_id="run-1",
                session_id=None,
                execution_mode=ExecutionMode.AGENT,
                request=PlanningReadRequest(path=path, start_byte=0, end_byte=8),
            )

        with pytest.raises(LoopToolBlocked):
            read(".env.local/db.txt")
        assert read("config/db.txt") is not None
    finally:
        os.rmdir(alias)  # remove the junction itself, never through it
