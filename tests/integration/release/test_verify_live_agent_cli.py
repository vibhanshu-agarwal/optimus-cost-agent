from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp import operator_verify
from optimus.acp.e2e_transcript import E2eAcpTranscriptWriter
from optimus.acp.operator_verify import OperatorLiveSessionResult, main, tool_trajectory_from_transcript
from optimus.acp.preflight import PreflightCheckResult


def _patch_transcript_path(monkeypatch, tmp_path: Path) -> Path:
    transcript_path = tmp_path / "plan-9-6-live-agent-transcript.json"
    monkeypatch.setattr(
        operator_verify,
        "default_live_agent_transcript_path",
        lambda repository_root: transcript_path,
    )
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


def test_verify_live_agent_documents_the_one_time_approval_prerequisite():
    """Plan 9.96, Task 5 Batch 3: this tool's spawned `python -m optimus.acp`
    child now runs through the gated __main__.py and requires a durable
    approval for the scratch verify workspace before it will do anything.
    The module's TOP-LEVEL docstring must say so explicitly, naming the
    EXACT workspace-root path this tool uses -- so the prerequisite is
    discoverable without a failed run, and a wrong path in the instructions
    doesn't become its own silent failure. Checked against the actual
    module docstring object (not just "somewhere in the file"), so a
    prerequisite note buried in an unrelated comment or docstring elsewhere
    would not satisfy this test."""
    module_docstring = operator_verify.__doc__ or ""

    assert "optimus-trust" in module_docstring
    assert "approve" in module_docstring
    assert "reports/.verify-live-agent-workspace" in module_docstring


def test_default_verify_workspace_root_is_gitignored_scratch_dir(tmp_path):
    scratch = operator_verify.default_verify_workspace_root(tmp_path)
    assert scratch == (tmp_path / "reports" / ".verify-live-agent-workspace").resolve()


def test_default_report_path_uses_explicit_repository_root(tmp_path):
    assert operator_verify.default_live_agent_transcript_path(tmp_path) == (
        tmp_path / "reports" / "plan-9-6-live-agent-transcript.json"
    ).resolve()


def test_verify_live_agent_defaults_to_scratch_workspace(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPTIMUS_GATEWAY_URL", "https://gateway.example")
    monkeypatch.setenv("OPTIMUS_API_KEY", "opt-test")
    monkeypatch.setenv("OPTIMUS_REDIS_URL", "redis://127.0.0.1:6379/0")
    _patch_transcript_path(monkeypatch, tmp_path)
    observed_workspace: list[Path] = []

    def _passing_checks(environ, **kwargs):
        observed_workspace.append(kwargs["workspace_root"])
        return [PreflightCheckResult(name="gateway credentials", passed=True, detail="present")]

    def _fake_session(config, *, environ, transcript, approval_callback=None):
        observed_workspace.append(config.workspace_root)
        return OperatorLiveSessionResult(success=True, stop_reason="plan_only", run_id="run-1")

    monkeypatch.setattr(operator_verify, "collect_preflight_checks", _passing_checks)
    monkeypatch.setattr(operator_verify, "run_operator_live_session", _fake_session)

    exit_code = main(["--plan-only"], repository_root=tmp_path)

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

    exit_code = main(["--workspace-root", str(tmp_path)], repository_root=tmp_path)

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "gateway auth" in captured.out
    assert "rejected" in captured.err


def test_tool_trajectory_from_transcript_accepts_post_36_tool_call_shape():
    transcript = E2eAcpTranscriptWriter()
    transcript.record_inbound(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "file_reader",
                    "toolCallId": "tool-1",
                }
            },
        }
    )
    transcript.record_inbound(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call",
                    "title": "write_file",
                    "toolCallId": "tool-2",
                }
            },
        }
    )
    transcript.record_inbound(
        {
            "method": "session/update",
            "params": {
                "update": {
                    "sessionUpdate": "tool_call_update",
                    "toolCall": {"title": "legacy_reader"},
                }
            },
        }
    )

    assert tool_trajectory_from_transcript(transcript) == [
        "file_reader",
        "write_file",
        "legacy_reader",
    ]


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
                        "sessionUpdate": "tool_call",
                        "title": "file_reader",
                        "toolCallId": "tool-1",
                    }
                },
            }
        )
        transcript.record_inbound(
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call",
                        "title": "write_file",
                        "toolCallId": "tool-2",
                    }
                },
            }
        )
        transcript.record_inbound(
            {
                "method": "session/update",
                "params": {
                    "update": {
                        "sessionUpdate": "tool_call_update",
                        "toolCall": {"title": "legacy_reader"},
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

    exit_code = main(["--workspace-root", str(tmp_path)], repository_root=tmp_path)
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "PASS: Optimus live agent verification completed." in output
    assert "prompt_version:" in output
    assert "plan_hash: abc123" in output
    assert "tool_trajectory: file_reader, write_file, legacy_reader" in output
    assert transcript_file.is_file()


def test_run_operator_live_session_surfaces_no_approval_remediation(tmp_path, monkeypatch):
    """Plan 9.96, Task 5 Batch 3: the spawned `python -m optimus.acp` child now
    runs through the gated __main__.py, which exits 2 with a value-free
    NO_APPROVAL message on stderr when no durable approval exists for the
    verify workspace. run_operator_live_session must detect that specific
    failure and raise a LiveSessionError whose message names the exact
    one-time `optimus-trust ... approve` command the operator needs to run —
    not a generic "subprocess exited early" message with no next step.

    This is a REAL subprocess (not a mock): a stand-in child that reproduces
    __main__.py's actual behavior on this path (prints the NO_APPROVAL
    message to stderr, exits 2 before writing anything to stdout) is spawned
    for real, so the detection logic is proven against real process
    exit/stderr semantics, not an assumption about them.
    """
    import sys as _sys

    from optimus.acp import operator_verify as operator_verify_module
    from optimus.acp.ndjson_subprocess_session import LiveSessionError

    workspace = tmp_path / "verify-workspace"
    workspace.mkdir()

    # A real stand-in child reproducing __main__.py's actual NO_APPROVAL
    # behavior on this path: prints the remediation to stderr, writes
    # nothing to stdout, exits 2. Uses repr() for the workspace path so a
    # Windows backslash path round-trips through the generated .py source
    # correctly (an unescaped backslash path caused a SyntaxError in the
    # child on the first attempt at this test, which is exactly the kind of
    # thing this comment exists to prevent happening silently again).
    fake_agent_script = tmp_path / "fake_gated_agent.py"
    fake_agent_script.write_text(
        "import sys\n"
        "print(\n"
        "    'optimus-agent: no launch approval found for this workspace. Review the effective '\n"
        "    'configuration and author one with:\\n'\n"
        f"    '  optimus-trust --workspace-root ' + {str(workspace)!r} + ' approve --mode durable',\n"
        "    file=sys.stderr,\n"
        ")\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )

    def fake_popen(args, **kwargs):
        # Replace the real `-m optimus.acp` invocation with the stand-in
        # script while preserving every other Popen kwarg (env, pipes, text
        # mode) so the REAL NdjsonSubprocessSession/session-reader machinery
        # runs against a REAL spawned process.
        return _real_popen([_sys.executable, str(fake_agent_script)], **kwargs)

    import subprocess as subprocess_module

    _real_popen = subprocess_module.Popen
    monkeypatch.setattr(operator_verify_module.subprocess, "Popen", fake_popen)

    class _FakeRedisStore:
        redis_client = None

        def latest_plan_for_run(self, *, run_id):
            return None

    monkeypatch.setattr(
        operator_verify_module.RedisAgentStateStore, "from_url", staticmethod(lambda url: _FakeRedisStore())
    )

    config = operator_verify_module.OperatorLiveSessionConfig(
        workspace_root=workspace,
        repository_root=tmp_path,
        model="claude-haiku",
        task="irrelevant",
        transcript_path=tmp_path / "transcript.json",
        wall_clock_timeout_seconds=10,
    )
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "test-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    }
    transcript = operator_verify_module.E2eAcpTranscriptWriter()

    with pytest.raises(LiveSessionError) as exc_info:
        operator_verify_module.run_operator_live_session(config, environ=environ, transcript=transcript)

    message = str(exc_info.value)
    assert "optimus-trust" in message
    assert "approve" in message
    assert str(workspace) in message
    # Must be a CLEAN, targeted remediation -- not the current generic
    # behavior of dumping raw stderr behind a "timed out waiting for
    # JSON-RPC response" preamble that never actually timed out (the child
    # exited immediately). A message that merely happens to CONTAIN the
    # remediation buried inside a misleading "timed out" wrapper is not
    # what an operator should see; this assertion is what keeps the test
    # from passing vacuously off the existing stderr-dump behavior.
    assert "timed out waiting" not in message
    assert "no launch approval found" in message


def test_run_operator_live_session_surfaces_config_root_rejection_cleanly(tmp_path, monkeypatch):
    """Plan 9.96, Task 5 Batch 3 review finding: the gate-rejection detector
    in ndjson_subprocess_session.py claims EVERY __main__.py error print
    carries the "optimus-agent: " prefix, including
    OperatorPathConfigurationError messages (e.g. a workspace-contained
    OPTIMUS_CONFIG_ROOT). This is a SEPARATE rejection family from
    NO_APPROVAL/SNAPSHOT_MISMATCH (a different exception type, handled by a
    different except block in __main__.py's _authorize_or_exit), so the
    NO_APPROVAL real-subprocess test above does not exercise it. This test
    proves the detector's invariant against that second family too, with a
    REAL spawned stand-in child (not a mock) reproducing __main__.py's
    actual OperatorPathConfigurationError print+exit behavior.
    """
    import sys as _sys

    from optimus.acp import operator_verify as operator_verify_module
    from optimus.acp.ndjson_subprocess_session import LiveSessionError

    workspace = tmp_path / "verify-workspace"
    workspace.mkdir()

    # A real stand-in child reproducing __main__.py's actual
    # OperatorPathConfigurationError behavior: prints the prefixed
    # "Refusing to load local gateway configuration..." message to stderr,
    # writes nothing to stdout, exits 2.
    fake_agent_script = tmp_path / "fake_config_root_rejecting_agent.py"
    fake_agent_script.write_text(
        "import sys\n"
        "print(\n"
        "    'optimus-agent: Refusing to load local gateway configuration from '\n"
        f"    + {str(workspace / 'config')!r}\n"
        "    + ' because it is inside workspace '\n"
        f"    + {str(workspace)!r}\n"
        "    + '. Set OPTIMUS_CONFIG_ROOT to an absolute directory outside the workspace.',\n"
        "    file=sys.stderr,\n"
        ")\n"
        "sys.exit(2)\n",
        encoding="utf-8",
    )

    def fake_popen(args, **kwargs):
        return _real_popen([_sys.executable, str(fake_agent_script)], **kwargs)

    import subprocess as subprocess_module

    _real_popen = subprocess_module.Popen
    monkeypatch.setattr(operator_verify_module.subprocess, "Popen", fake_popen)

    class _FakeRedisStore:
        redis_client = None

        def latest_plan_for_run(self, *, run_id):
            return None

    monkeypatch.setattr(
        operator_verify_module.RedisAgentStateStore, "from_url", staticmethod(lambda url: _FakeRedisStore())
    )

    config = operator_verify_module.OperatorLiveSessionConfig(
        workspace_root=workspace,
        repository_root=tmp_path,
        model="claude-haiku",
        task="irrelevant",
        transcript_path=tmp_path / "transcript.json",
        wall_clock_timeout_seconds=10,
    )
    environ = {
        "OPTIMUS_GATEWAY_URL": "http://127.0.0.1:8765",
        "OPTIMUS_API_KEY": "test-key",
        "OPTIMUS_REDIS_URL": "redis://127.0.0.1:6379/0",
    }
    transcript = operator_verify_module.E2eAcpTranscriptWriter()

    with pytest.raises(LiveSessionError) as exc_info:
        operator_verify_module.run_operator_live_session(config, environ=environ, transcript=transcript)

    message = str(exc_info.value)
    assert "Refusing to load local gateway configuration" in message
    assert "OPTIMUS_CONFIG_ROOT" in message
    # Same anti-vacuous-pass guard as the NO_APPROVAL test: must be the
    # clean message, not the generic stderr dump behind a misleading
    # "timed out waiting" wrapper.
    assert "timed out waiting" not in message


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

    exit_code = main(["--workspace-root", str(tmp_path)], repository_root=tmp_path)

    assert exit_code == 3
    assert "stopReason mismatch" in capsys.readouterr().err
    assert transcript_file.is_file()
