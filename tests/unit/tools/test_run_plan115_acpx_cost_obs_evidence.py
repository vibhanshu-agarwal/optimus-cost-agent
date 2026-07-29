"""Unit tests for the Plan 11.5 Task 8 E7 acpx cost-observability evidence helper.

Binding Task 8 constraints under test here:
- The script invokes an EXTERNAL ``acpx`` executable (never a project ACP client).
- The script never imports the project's own ACP protocol implementation, server,
  dispatcher, or any project-authored ACP client/test harness.
- Any ACP result containing a retired accounting field name (assembled below)
  is rejected.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from optimus.acp.subprocess_env import SubprocessEnvConfigurationError
from tools.run_plan115_acpx_cost_obs_evidence import (
    _DISALLOWED_PROJECT_ACP_MODULES,
    FORBIDDEN_RESULT_FIELDS,
    AcpxNotFoundError,
    RetiredAccountingFieldError,
    assert_agent_environment_is_approved,
    assert_no_retired_accounting_fields,
    build_acpx_command,
    build_agent_invocation,
    build_e7_summary,
    extract_acp_results,
    parse_jsonl_records,
    resolve_acpx,
    resolve_optimus_agent,
    verify_acp_results,
)

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "tools" / "run_plan115_acpx_cost_obs_evidence.py"
_RETIRED = "cred" + "it"
_FORBIDDEN_LEDGER_TOTAL = f"ledger_run_total_{_RETIRED}s"
_FORBIDDEN_OPTIMUS_DEBITED = f"optimus_{_RETIRED}s_debited"


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
    for disallowed in _DISALLOWED_PROJECT_ACP_MODULES:
        assert disallowed not in imported, f"script must never import {disallowed}"


def test_disallowed_module_list_is_non_empty_and_covers_known_acp_protocol_surfaces() -> None:
    # Guards against an empty/no-op denylist silently making the test above vacuous.
    assert "optimus.acp.dispatcher" in _DISALLOWED_PROJECT_ACP_MODULES
    assert "optimus.acp.server" in _DISALLOWED_PROJECT_ACP_MODULES
    assert "optimus.acp.ndjson_subprocess_session" in _DISALLOWED_PROJECT_ACP_MODULES


def test_resolve_acpx_uses_shutil_which_for_the_external_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_which(name: str) -> str | None:
        calls.append(name)
        return r"C:\tools\acpx.exe" if name == "acpx" else None

    monkeypatch.setattr("tools.run_plan115_acpx_cost_obs_evidence.shutil.which", fake_which)
    resolved = resolve_acpx()

    assert resolved == r"C:\tools\acpx.exe"
    assert calls == ["acpx"]


def test_resolve_acpx_fails_closed_when_acpx_is_not_on_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.run_plan115_acpx_cost_obs_evidence.shutil.which", lambda _name: None)

    with pytest.raises(AcpxNotFoundError, match="acpx not found on PATH"):
        resolve_acpx()


def test_resolve_optimus_agent_fails_closed_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("tools.run_plan115_acpx_cost_obs_evidence.shutil.which", lambda _name: None)

    with pytest.raises(AcpxNotFoundError, match="optimus-agent not found on PATH"):
        resolve_optimus_agent()


def test_build_acpx_command_invokes_the_resolved_external_acpx_binary(tmp_path: Path) -> None:
    command = build_acpx_command(
        acpx="/usr/local/bin/acpx",
        workspace=tmp_path,
        agent_invocation="optimus-agent --workspace-root /ws",
        task="do the thing",
    )

    assert command[0] == "/usr/local/bin/acpx"
    assert "exec" in command
    assert command[-1] == "do the thing"
    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "optimus-agent --workspace-root /ws"


def test_build_agent_invocation_uses_forward_slashes_for_acpx_parsing(tmp_path: Path) -> None:
    invocation = build_agent_invocation(agent_exe=r"C:\tools\optimus-agent.exe", workspace=tmp_path)

    assert "\\" not in invocation
    assert invocation.startswith("C:/tools/optimus-agent.exe")


def test_build_agent_invocation_omits_phoenix_by_default(tmp_path: Path) -> None:
    invocation = build_agent_invocation(agent_exe="optimus-agent", workspace=tmp_path)
    assert "--with-local-phoenix" not in invocation


def test_build_agent_invocation_opts_into_local_phoenix(tmp_path: Path) -> None:
    invocation = build_agent_invocation(
        agent_exe="optimus-agent",
        workspace=tmp_path,
        with_local_phoenix=True,
    )
    assert "--with-local-phoenix" in invocation


def test_run_capture_passes_with_local_phoenix_true(monkeypatch, tmp_path: Path) -> None:
    """Plan 11.6 Task 3: cost-observability capture opts into Phoenix explicitly."""
    from tools import run_plan115_acpx_cost_obs_evidence as tool

    observed: dict[str, object] = {}

    monkeypatch.setattr(tool, "resolve_acpx", lambda: "/usr/bin/acpx")
    monkeypatch.setattr(tool, "resolve_optimus_agent", lambda: "optimus-agent")
    monkeypatch.setattr(tool, "build_agent_environment", lambda _env: {"PATH": "/usr/bin"})
    monkeypatch.setattr(tool, "assert_agent_environment_is_approved", lambda _env: None)

    def fake_invocation(*, agent_exe, workspace, with_local_phoenix=False):
        observed["with_local_phoenix"] = with_local_phoenix
        return f"{agent_exe} --workspace-root {workspace.as_posix()}"

    monkeypatch.setattr(tool, "build_agent_invocation", fake_invocation)
    monkeypatch.setattr(
        tool,
        "build_acpx_command",
        lambda **k: ["acpx", "exec", "task"],
    )
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )
    monkeypatch.setattr(tool, "parse_jsonl_records", lambda _t: [])
    monkeypatch.setattr(tool, "verify_acp_results", lambda _r: [])
    monkeypatch.setattr(tool, "build_e7_summary", lambda **k: {"ok": True})
    monkeypatch.setattr(tool, "write_e7_report", lambda *a, **k: None)

    tool.run_capture(workspace=tmp_path, task="smoke", report_path=tmp_path / "r.md")

    assert observed["with_local_phoenix"] is True


def test_assert_no_retired_accounting_fields_passes_on_current_ledger_field_names() -> None:
    current_result = {
        "gateway_usage": {"cost_usd": "0.01", "billing_units": 5},
        "ledger_run_total_cost_usd": "0.05",
        "ledger_run_total_billing_units": 25,
    }

    assert_no_retired_accounting_fields(current_result)  # must not raise


@pytest.mark.parametrize("forbidden_field", FORBIDDEN_RESULT_FIELDS)
def test_assert_no_retired_accounting_fields_rejects_top_level_forbidden_field(forbidden_field: str) -> None:
    result = {"gateway_usage": {"cost_usd": "0.01"}, forbidden_field: 7}

    with pytest.raises(RetiredAccountingFieldError) as excinfo:
        assert_no_retired_accounting_fields(result)
    assert any(forbidden_field in path for path in excinfo.value.field_paths)


@pytest.mark.parametrize("forbidden_field", FORBIDDEN_RESULT_FIELDS)
def test_assert_no_retired_accounting_fields_rejects_nested_forbidden_field(forbidden_field: str) -> None:
    result = {"results": [{"gateway_usage": {forbidden_field: "1.23"}}]}

    with pytest.raises(RetiredAccountingFieldError):
        assert_no_retired_accounting_fields(result)


def test_forbidden_result_fields_match_assembled_retired_names() -> None:
    assert FORBIDDEN_RESULT_FIELDS == (_FORBIDDEN_LEDGER_TOTAL, _FORBIDDEN_OPTIMUS_DEBITED)


def test_extract_acp_results_collects_every_result_object() -> None:
    records = [
        {"jsonrpc": "2.0", "id": 1, "result": {"a": 1}},
        {"jsonrpc": "2.0", "method": "session/update", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"b": 2}},
    ]

    results = extract_acp_results(records)

    assert results == [{"a": 1}, {"b": 2}]


def test_verify_acp_results_passes_on_clean_transcript() -> None:
    records = [{"id": 1, "result": {"ledger_run_total_cost_usd": "0.02", "ledger_run_total_billing_units": 3}}]

    results = verify_acp_results(records)

    assert len(results) == 1


def test_verify_acp_results_rejects_transcript_with_a_retired_field_anywhere() -> None:
    records = [
        {"id": 1, "result": {"ledger_run_total_cost_usd": "0.02"}},
        {"id": 2, "result": {_FORBIDDEN_LEDGER_TOTAL: 7}},
    ]

    with pytest.raises(RetiredAccountingFieldError):
        verify_acp_results(records)


def test_parse_jsonl_records_skips_blank_and_non_json_lines() -> None:
    transcript = '{"id": 1, "result": {"ok": true}}\n\nnot json\n{"id": 2, "result": {"ok": false}}\n'

    records = parse_jsonl_records(transcript)

    assert len(records) == 2
    assert records[0]["result"]["ok"] is True
    assert records[1]["result"]["ok"] is False


def test_parse_jsonl_records_skips_non_object_json_lines() -> None:
    transcript = '[1, 2, 3]\n"just a string"\n{"id": 1, "result": {"ok": true}}\n'

    records = parse_jsonl_records(transcript)

    assert records == [{"id": 1, "result": {"ok": True}}]


def test_build_agent_environment_accepts_empty_optimus_projection() -> None:
    """Plan 11.6 Task 1: evidence helper must accept a PATH-only / zero-Optimus shell."""
    from tools.run_plan115_acpx_cost_obs_evidence import build_agent_environment

    env = build_agent_environment({"PATH": "/usr/bin"})
    assert env == {"PATH": "/usr/bin"}
    assert_agent_environment_is_approved(env)
    assert not any(name.startswith("OPTIMUS_") for name in env)


def test_assert_agent_environment_is_approved_accepts_registry_names() -> None:
    env = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        "OPTIMUS_API_KEY": "secret",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        "PATH": "/usr/bin",
    }

    assert_agent_environment_is_approved(env)  # must not raise


def test_assert_agent_environment_is_approved_rejects_unapproved_name() -> None:
    env = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9",
        "OPTIMUS_API_KEY": "secret",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
        "ANTHROPIC_API_KEY": "should-never-be-here",
    }

    with pytest.raises(SubprocessEnvConfigurationError, match="ANTHROPIC_API_KEY"):
        assert_agent_environment_is_approved(env)


def test_build_e7_summary_records_usd_and_billing_unit_evidence_and_legacy_absence() -> None:
    results = [
        {
            "gateway_usage": {"cost_usd": "0.0015", "billing_units": 10},
            "ledger_run_total_cost_usd": "0.0015",
            "ledger_run_total_billing_units": 10,
        }
    ]
    env = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9", "OPTIMUS_API_KEY": "x", "OPTIMUS_REDIS_URL": "redis://x"}

    summary = build_e7_summary(results=results, env=env, exit_code=0)

    assert summary["legacy_fields_absent"] is True
    assert summary["capture_complete"] is True
    assert summary["legacy_fields_checked"] == list(FORBIDDEN_RESULT_FIELDS)
    assert summary["result_count"] == 1
    field_paths = {field["path"] for field in summary["cost_evidence_fields"]}
    assert any(path.endswith("cost_usd") for path in field_paths)
    assert any(path.endswith("billing_units") for path in field_paths)
    assert "acpx_client" in summary
    assert "project ACP client" in summary["acpx_client"]


def test_build_e7_summary_marks_incomplete_when_no_acp_results() -> None:
    env = {"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9", "OPTIMUS_API_KEY": "x", "OPTIMUS_REDIS_URL": "redis://x"}

    summary = build_e7_summary(results=[], env=env, exit_code=2)

    assert summary["result_count"] == 0
    assert summary["capture_complete"] is False
    assert summary["legacy_fields_absent"] is None
    assert summary["cost_evidence_fields"] == []


def test_write_e7_report_persists_sanitized_transcript_only(tmp_path: Path) -> None:
    from tools.run_plan115_acpx_cost_obs_evidence import _sanitize_full_text, write_e7_report

    secret = "super-secret-gateway-key-value"
    sanitized_stdout = _sanitize_full_text(f"seen {secret} in stdout", known_secrets=(secret,))
    sanitized_stderr = _sanitize_full_text(f"seen {secret} in stderr", known_secrets=(secret,))
    report_path = tmp_path / "e7.md"

    write_e7_report(
        report_path,
        summary={"schema_version": "plan-11-5-e7-acpx-cost-obs-evidence-v1", "legacy_fields_absent": True},
        sanitized_stdout=sanitized_stdout,
        sanitized_stderr=sanitized_stderr,
    )

    text = report_path.read_text(encoding="utf-8")
    assert secret not in text
    assert "seen" in text
