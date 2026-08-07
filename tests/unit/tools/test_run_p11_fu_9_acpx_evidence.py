"""Unit tests for the P11-FU-9 Task 8 acpx live-evidence helper.

Binding constraints under test:
- Invokes independent ``acpx`` (never a project ACP client).
- Asserts ``git check-ignore -q`` for scratch paths before writing.
- Parses only safe JSONL fields into reports (no raw secrets/transcript dumps).
- Builds Windows-safe ``agents.optimus-fu9.argv`` and ``--mcp-config`` argv.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from tools.run_p11_fu_9_acpx_evidence import (
    DISALLOWED_PROJECT_ACP_MODULES,
    SCRATCH_IGNORE_CANDIDATES,
    AcpxEvidenceError,
    AcpxNotFoundError,
    assert_report_has_no_secrets,
    assert_scratch_paths_ignored,
    build_acpx_command,
    build_acpxrc_document,
    build_evidence_summary,
    build_mcp_servers_document,
    extract_safe_evidence,
    parse_jsonl_records,
    resolve_acpx,
    write_scratch_configs,
)

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "tools" / "run_p11_fu_9_acpx_evidence.py"


def _imported_module_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_script_never_imports_a_project_acp_client_or_protocol_module() -> None:
    tree = ast.parse(_SCRIPT_PATH.read_text(encoding="utf-8"))
    imported = _imported_module_names(tree)
    for disallowed in DISALLOWED_PROJECT_ACP_MODULES:
        assert disallowed not in imported, f"script must never import {disallowed}"


def test_disallowed_module_list_covers_known_acp_protocol_surfaces() -> None:
    assert "optimus.acp.dispatcher" in DISALLOWED_PROJECT_ACP_MODULES
    assert "optimus.acp.server" in DISALLOWED_PROJECT_ACP_MODULES
    assert "optimus.acp.ndjson_subprocess_session" in DISALLOWED_PROJECT_ACP_MODULES


def test_scratch_ignore_candidates_cover_plan_paths() -> None:
    assert ".acpxrc.json" in SCRATCH_IGNORE_CANDIDATES
    assert "mcpServers.json" in SCRATCH_IGNORE_CANDIDATES
    assert "tmp/" in SCRATCH_IGNORE_CANDIDATES


def test_assert_scratch_paths_ignored_fails_closed_when_git_check_ignore_misses(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        return type("P", (), {"returncode": 1})()

    monkeypatch.setattr("tools.run_p11_fu_9_acpx_evidence.subprocess.run", fake_run)

    with pytest.raises(AcpxEvidenceError, match="check-ignore"):
        assert_scratch_paths_ignored(repo_root=tmp_path)

    assert calls
    assert calls[0][:3] == ["git", "check-ignore", "-q"]


def test_assert_scratch_paths_ignored_falls_back_to_gitignore_when_git_unusable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".gitignore").write_text(".acpxrc.json\nmcpServers.json\ntmp/\n", encoding="utf-8")
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.subprocess.run",
        lambda *_a, **_k: type("P", (), {"returncode": 128})(),
    )
    assert_scratch_paths_ignored(repo_root=tmp_path)  # must not raise


def test_assert_scratch_paths_ignored_fails_when_gitignore_fallback_incomplete(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".gitignore").write_text(".acpxrc.json\n", encoding="utf-8")
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.subprocess.run",
        lambda *_a, **_k: type("P", (), {"returncode": 128})(),
    )
    with pytest.raises(AcpxEvidenceError, match="missing scratch rules"):
        assert_scratch_paths_ignored(repo_root=tmp_path)


def test_assert_scratch_paths_ignored_passes_when_all_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.subprocess.run",
        lambda *_a, **_k: type("P", (), {"returncode": 0})(),
    )
    assert_scratch_paths_ignored(repo_root=tmp_path)  # must not raise


def test_resolve_acpx_uses_shutil_which_for_the_external_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.shutil.which",
        lambda name: r"C:\tools\acpx.exe" if name == "acpx" else None,
    )
    assert resolve_acpx() == r"C:\tools\acpx.exe"


def test_resolve_acpx_fails_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.run_p11_fu_9_acpx_evidence.shutil.which", lambda _name: None)
    with pytest.raises(AcpxNotFoundError, match="acpx not found"):
        resolve_acpx()


def test_build_acpxrc_document_uses_windows_safe_argv_array() -> None:
    doc = build_acpxrc_document(agent_argv=[r"C:\tools\optimus-agent.exe", "--workspace-root", "D:/ws"])
    assert doc == {
        "agents": {
            "optimus-fu9": {
                "argv": [r"C:\tools\optimus-agent.exe", "--workspace-root", "D:/ws"],
            }
        }
    }
    assert "command" not in doc["agents"]["optimus-fu9"]


def test_build_mcp_servers_document_wraps_fixture_array() -> None:
    servers = [{"name": "docs", "type": "http", "url": "https://mcp.context7.com/mcp"}]
    doc = build_mcp_servers_document(servers)
    assert doc == {"mcpServers": servers}


def test_build_acpx_command_includes_mcp_config_format_approve_all_and_agent(
    tmp_path: Path,
) -> None:
    mcp_config = tmp_path / "mcpServers.json"
    command = build_acpx_command(
        acpx="/usr/local/bin/acpx",
        cwd=tmp_path,
        mcp_config=mcp_config,
        task="list mcp tools",
    )
    assert command[0] == "/usr/local/bin/acpx"
    assert "--mcp-config" in command
    assert command[command.index("--mcp-config") + 1] == str(mcp_config)
    assert "--format" in command and command[command.index("--format") + 1] == "json"
    assert "--approve-all" in command
    assert "--cwd" in command and command[command.index("--cwd") + 1] == str(tmp_path)
    assert "optimus-fu9" in command
    assert "exec" in command
    assert command[-1] == "list mcp tools"
    assert all(isinstance(part, str) for part in command)


def test_write_scratch_configs_writes_ignored_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.subprocess.run",
        lambda *_a, **_k: type("P", (), {"returncode": 0})(),
    )
    paths = write_scratch_configs(
        scratch_dir=tmp_path,
        repo_root=tmp_path,
        agent_argv=["optimus-agent", "--workspace-root", str(tmp_path)],
        mcp_servers=[{"name": "t", "command": "echo"}],
    )
    assert paths.acpxrc.is_file()
    assert paths.mcp_servers.is_file()
    acpxrc = json.loads(paths.acpxrc.read_text(encoding="utf-8"))
    assert acpxrc["agents"]["optimus-fu9"]["argv"][0] == "optimus-agent"
    mcp = json.loads(paths.mcp_servers.read_text(encoding="utf-8"))
    assert mcp["mcpServers"][0]["name"] == "t"


def test_parse_jsonl_records_skips_non_object_lines() -> None:
    transcript = '{"id": 1, "result": {"sessionId": "s1"}}\n\nnot-json\n[1]\n{"method": "x"}\n'
    records = parse_jsonl_records(transcript)
    assert records == [{"id": 1, "result": {"sessionId": "s1"}}, {"method": "x"}]


def test_extract_safe_evidence_keeps_only_content_free_fields() -> None:
    records = [
        {
            "jsonrpc": "2.0",
            "id": 0,
            "result": {
                "protocolVersion": 1,
                "agentCapabilities": {"mcpCapabilities": {"http": False, "sse": False}},
                "agentInfo": {"name": "optimus", "version": "0.1.0"},
            },
        },
        {"jsonrpc": "2.0", "id": 1, "result": {"sessionId": "session-abc"}},
        {
            "jsonrpc": "2.0",
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "mcp_list_tools",
                    "rawSecret": "sk-live-SHOULD-NOT-APPEAR",
                }
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "session/request_permission",
            "params": {
                "options": [{"optionId": "allow_once"}, {"optionId": "reject_once"}],
                "toolCall": {"title": "mcp_call"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "result": {"stopReason": "end_turn"}},
    ]
    evidence = extract_safe_evidence(
        records,
        acpx_path=r"C:\tools\acpx.exe",
        acpx_version="0.12.0",
        exit_code=0,
    )
    payload = json.dumps(evidence)
    assert "sk-live" not in payload
    assert evidence["acpx_version"] == "0.12.0"
    expected_digest = hashlib.sha256(r"C:\tools\acpx.exe".encode("utf-8")).hexdigest()
    assert evidence["acpx_path_digest"] == expected_digest
    assert evidence["acp_protocol_version"] == 1
    assert evidence["session_id"] == "session-abc"
    assert evidence["stop_reason"] == "end_turn"
    assert evidence["mcp_capabilities"] == {"http": False, "sse": False}
    assert "mcp_list_tools" in evidence["tool_call_titles"]
    assert "allow_once" in evidence["permission_option_ids"]


def test_assert_report_has_no_secrets_rejects_known_secret_tokens() -> None:
    with pytest.raises(AcpxEvidenceError, match="secret"):
        assert_report_has_no_secrets(
            {"note": "bearer sk-ant-api03-CANARY_DO_NOT_USE"},
            known_secrets=("sk-ant-api03-CANARY_DO_NOT_USE",),
        )


def test_build_evidence_summary_marks_empty_array_noop() -> None:
    summary = build_evidence_summary(
        evidence={
            "acpx_version": "0.12.0",
            "acpx_path_digest": "a" * 64,
            "acp_protocol_version": 1,
            "session_id": "s1",
            "stop_reason": "end_turn",
            "mcp_capabilities": {"http": False, "sse": False},
            "tool_call_titles": [],
            "permission_option_ids": [],
            "exit_code": 0,
        },
        mcp_servers_count=0,
        capture_complete=True,
    )
    assert summary["empty_mcp_servers_noop"] is True
    assert summary["schema_version"] == "p11-fu-9-acpx-client-mcp-evidence-v1"
    assert summary["acpx_client"] == "external (independent acpx binary; no project ACP client used)"


def test_write_reports_persists_content_free_summary_only(tmp_path: Path) -> None:
    from tools.run_p11_fu_9_acpx_evidence import write_reports

    summary = {
        "schema_version": "p11-fu-9-acpx-client-mcp-evidence-v1",
        "session_id": "s1",
        "stop_reason": "end_turn",
        "empty_mcp_servers_noop": True,
    }
    md_path = tmp_path / "evidence.md"
    json_path = tmp_path / "evidence.json"
    write_reports(md_path=md_path, json_path=json_path, summary=summary)
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    assert loaded == summary
    body = md_path.read_text(encoding="utf-8")
    assert "s1" in body
    assert "sk-" not in body
    assert "OPTIMUS_API_KEY" not in body


def test_main_prints_controlled_stderr_when_acpx_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from tools.run_p11_fu_9_acpx_evidence import AcpxNotFoundError, main

    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.run_capture",
        lambda **_kwargs: (_ for _ in ()).throw(AcpxNotFoundError("acpx not found on PATH")),
    )
    code = main(
        [
            "--scratch-dir",
            str(tmp_path),
            "--repo-root",
            str(tmp_path),
            "--task",
            "noop",
            "--md-report",
            str(tmp_path / "out.md"),
            "--json-report",
            str(tmp_path / "out.json"),
        ]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "acpx not found" in err
    assert "sk-" not in err


def test_run_capture_writes_raw_transcript_only_under_ignored_scratch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tools.run_p11_fu_9_acpx_evidence import run_capture

    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.assert_scratch_paths_ignored",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr("tools.run_p11_fu_9_acpx_evidence.resolve_acpx", lambda: "acpx")
    monkeypatch.setattr("tools.run_p11_fu_9_acpx_evidence.acpx_version", lambda _acpx: "0.12.0")
    monkeypatch.setattr(
        "tools.run_p11_fu_9_acpx_evidence.resolve_optimus_agent",
        lambda: "optimus-agent",
    )

    transcript = (
        '{"jsonrpc":"2.0","id":1,"result":{"sessionId":"session-safe"}}\n'
        '{"jsonrpc":"2.0","id":2,"result":{"stopReason":"end_turn"}}\n'
    )

    def fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        return type("P", (), {"returncode": 0, "stdout": transcript, "stderr": "debug-line"})()

    monkeypatch.setattr("tools.run_p11_fu_9_acpx_evidence.subprocess.run", fake_run)

    md_path = tmp_path / "reports" / "out.md"
    json_path = tmp_path / "reports" / "out.json"
    code = run_capture(
        scratch_dir=tmp_path,
        repo_root=tmp_path,
        task="list mcp tools",
        mcp_servers=[],
        md_report=md_path,
        json_report=json_path,
        agent_argv=["optimus-agent", "--workspace-root", str(tmp_path)],
        known_secrets=("sk-ant-api03-CANARY_DO_NOT_USE",),
    )
    assert code == 0
    raw_out = (tmp_path / "tmp" / "acpx.stdout.jsonl").read_text(encoding="utf-8")
    raw_err = (tmp_path / "tmp" / "acpx.stderr.txt").read_text(encoding="utf-8")
    assert "session-safe" in raw_out
    assert raw_err == "debug-line"
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["session_id"] == "session-safe"
    assert report["stop_reason"] == "end_turn"
    assert "debug-line" not in json.dumps(report)
    assert "sk-ant-api03-CANARY_DO_NOT_USE" not in json.dumps(report)