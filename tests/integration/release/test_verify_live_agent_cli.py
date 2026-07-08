from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from optimus.acp import operator_verify
from optimus.acp.operator_verify import OperatorLiveSessionResult, main
from optimus.acp.preflight import PreflightCheckResult


def _patch_transcript_path(monkeypatch, tmp_path: Path) -> Path:
    transcript_path = tmp_path / "plan-9-6-live-agent-transcript.json"
    monkeypatch.setattr(operator_verify, "default_live_agent_transcript_path", lambda: transcript_path)
    return transcript_path


def test_verify_live_agent_module_exposes_required_flags():
    text = Path(operator_verify.__file__).read_text(encoding="utf-8")

    assert "--workspace-root" in text
    assert "default_verify_workspace_root" in text
    assert "reports/.verify-live-agent-workspace" in text
    assert "--model" in text
    assert "--task" in text
    assert "--plan-only" in text
    assert "--require-manual-approval" in text
    assert "--transcript-path" in text
    assert "default_live_agent_transcript_path" in text


def test_default_verify_workspace_root_is_gitignored_scratch_dir(tmp_path):
    scratch = operator_verify.default_verify_workspace_root(tmp_path)
    assert scratch == (tmp_path / "reports" / ".verify-live-agent-workspace").resolve()


def test_verify_live_agent_defaults_to_scratch_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    _patch_transcript_path(monkeypatch, tmp_path)
    monkeypatch.setattr(operator_verify, "_resolve_project_root", lambda: tmp_path)

    observed_workspace: list[Path] = []

    def _passing_checks(environ, **kwargs):
        observed_workspace.append(kwargs["workspace_root"])
        return [PreflightCheckResult(name="gateway credentials", passed=True, detail="present")]

    def _fake_session(config, *, environ, transcript, approval_callback=None):
        observed_workspace.append(config.workspace_root)
        return OperatorLiveSessionResult(success=True, stop_reason="plan_only", run_id="run-1")

    monkeypatch.setattr(operator_verify, "collect_preflight_checks", _passing_checks)
    monkeypatch.setattr(operator_verify, "run_operator_live_session", _fake_session)

    exit_code = main(["--plan-only"])

    assert exit_code == 0
    expected = operator_verify.default_verify_workspace_root(tmp_path)
    assert observed_workspace == [expected, expected]


def test_verify_live_agent_preflight_failure_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    _patch_transcript_path(monkeypatch, tmp_path)

    def _failed_checks(environ, **kwargs):
        return [PreflightCheckResult(name="gateway auth", passed=False, detail="rejected")]

    monkeypatch.setattr(operator_verify, "collect_preflight_checks", _failed_checks)

    exit_code = main(["--workspace-root", str(tmp_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "gateway auth" in captured.out
    assert "rejected" in captured.err


def test_verify_live_agent_success_exits_0(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    transcript_file = _patch_transcript_path(monkeypatch, tmp_path)

    def _passing_checks(environ, **kwargs):
        return [PreflightCheckResult(name="gateway credentials", passed=True, detail="present")]

    def _fake_session(config, *, environ, transcript, approval_callback=None):
        transcript.record_inbound(
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCall": {"title": "write_file"},
                    }
                },
            }
        )
        return OperatorLiveSessionResult(
            success=True,
            model="claude-haiku",
            plan_hash="abc123",
            approval_id="approval-1",
            total_cost_usd=Decimal("0.01"),
            stop_reason="end_turn",
            run_id="run-1",
        )

    monkeypatch.setattr(operator_verify, "collect_preflight_checks", _passing_checks)
    monkeypatch.setattr(operator_verify, "run_operator_live_session", _fake_session)

    exit_code = main(["--workspace-root", str(tmp_path)])
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS: Optimus live agent verification completed." in output
    assert "prompt_version:" in output
    assert "plan_hash: abc123" in output
    assert transcript_file.is_file()


def test_verify_live_agent_runtime_failure_exits_3(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    transcript_file = _patch_transcript_path(monkeypatch, tmp_path)

    def _passing_checks(environ, **kwargs):
        return [PreflightCheckResult(name="gateway credentials", passed=True, detail="present")]

    def _failed_session(config, *, environ, transcript, approval_callback=None):
        return OperatorLiveSessionResult(success=False, failure_message="stopReason mismatch")

    monkeypatch.setattr(operator_verify, "collect_preflight_checks", _passing_checks)
    monkeypatch.setattr(operator_verify, "run_operator_live_session", _failed_session)

    exit_code = main(["--workspace-root", str(tmp_path)])

    assert exit_code == 3
    assert "stopReason mismatch" in capsys.readouterr().err
    assert transcript_file.is_file()
