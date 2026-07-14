from __future__ import annotations

import json
import os

from optimus.acp import __main__ as acp_main
from optimus.acp.debug_trace import DEFAULT_DEBUG_LOG_RELATIVE_PATH, debug_trace_enabled, resolve_debug_log_path


def test_parse_args_accepts_debug_trace_flags():
    args = acp_main.parse_args(["--workspace-root", ".", "--debug-trace", "--debug-log", "logs/trace.ndjson"])
    assert args.debug_trace is True
    assert args.debug_log == "logs/trace.ndjson"


def test_resolve_debug_log_path_defaults_under_workspace_root(tmp_path):
    assert resolve_debug_log_path(workspace_root=tmp_path) == (tmp_path / DEFAULT_DEBUG_LOG_RELATIVE_PATH).resolve()


def test_resolve_debug_log_path_supports_relative_workspace_paths(tmp_path):
    assert resolve_debug_log_path(workspace_root=tmp_path, log_path="reports/trace.ndjson") == (
        tmp_path / "reports/trace.ndjson"
    ).resolve()


def test_check_config_with_debug_trace_writes_default_provenance_log(monkeypatch, tmp_path):
    monkeypatch.delenv("OPTIMUS_ACP_DEBUG_TRACE", raising=False)
    monkeypatch.delenv("OPTIMUS_ACP_DEBUG_LOG", raising=False)
    import optimus.acp.debug_trace as debug_trace_module

    monkeypatch.setattr(debug_trace_module, "_PROVENANCE_LOGGED", False)
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, config_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        },
    )
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **kwargs: "redis://127.0.0.1:6379/0")

    exit_code = acp_main.main(["--workspace-root", str(tmp_path), "--check-config", "--debug-trace"])

    log_path = (tmp_path / DEFAULT_DEBUG_LOG_RELATIVE_PATH).resolve()
    assert exit_code == 0
    assert debug_trace_enabled()
    assert os.environ["OPTIMUS_ACP_DEBUG_LOG"] == str(log_path)
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["hypothesisId"] == "PROVENANCE"
    assert payload["data"]["log_path"] == str(log_path)


def test_log_workspace_context_result_redacts_source_content(monkeypatch, tmp_path):
    log_path = tmp_path / "trace.ndjson"
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_TRACE", "1")
    monkeypatch.setenv("OPTIMUS_ACP_DEBUG_LOG", str(log_path))

    from optimus.acp.debug_trace import log_workspace_context_result
    from optimus.agent.models import AgentRunRequest
    from optimus.agent.workspace_context import WorkspaceContextResult
    from optimus.runtime.modes import ExecutionMode

    request = AgentRunRequest(
        run_id="run-1",
        session_id="session-1",
        task="Edit example.py",
        execution_mode=ExecutionMode.PLAN,
        workspace_root=tmp_path,
    )
    result = WorkspaceContextResult(
        text="--- src/example.py ---\nUNIQUE_SECRET_SENTINEL\n",
        max_total_bytes=16 * 1024,
        used_bytes=42,
        prioritized_paths=("src/example.py",),
        omitted_paths=(),
        diagnostics=(),
    )

    log_workspace_context_result(request, result)

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["hypothesisId"] == "P9.8-CONTEXT"
    assert payload["data"]["prioritized_paths"] == ["src/example.py"]
    assert payload["data"]["used_bytes"] > 0
    assert "UNIQUE_SECRET_SENTINEL" not in log_path.read_text(encoding="utf-8")


def test_check_config_with_relative_debug_log_path(monkeypatch, tmp_path):
    monkeypatch.delenv("OPTIMUS_ACP_DEBUG_TRACE", raising=False)
    monkeypatch.delenv("OPTIMUS_ACP_DEBUG_LOG", raising=False)
    import optimus.acp.debug_trace as debug_trace_module

    monkeypatch.setattr(debug_trace_module, "_PROVENANCE_LOGGED", False)
    monkeypatch.setattr(
        acp_main,
        "apply_local_defaults",
        lambda environ, *, config_root: {
            "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
            "OPTIMUS_API_KEY": "test-key",
            "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        },
    )
    monkeypatch.setattr(acp_main, "ensure_local_redis", lambda *a, **k: None)
    monkeypatch.setattr(acp_main, "run_preflight", lambda environ, **kwargs: "redis://127.0.0.1:6379/0")

    exit_code = acp_main.main(
        [
            "--workspace-root",
            str(tmp_path),
            "--check-config",
            "--debug-trace",
            "--debug-log",
            "reports/issue-33.ndjson",
        ]
    )

    log_path = (tmp_path / "reports/issue-33.ndjson").resolve()
    assert exit_code == 0
    assert log_path.exists()
