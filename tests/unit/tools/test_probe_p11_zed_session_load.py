"""Unit contracts for the version-agnostic P11 Zed session/load re-probe."""

from __future__ import annotations

import json
from pathlib import Path

from tools.probe_p11_zed_session_load import (
    CommandResult,
    Finding,
    build_acpx_command,
    build_cleanup_remediation,
    build_trust_command,
    capture_acpx_evidence,
    classify_indeterminate_context,
    evaluate_session_load_exchange,
    extract_acpx_archive_capability_payload,
)


def test_reachable_requires_advertised_capability_and_real_result() -> None:
    """Catches a false positive when a successful response lacks load capability."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {"resume": False}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "result": {"sessionId": "saved-1"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.REACHABLE
    assert result.capability_payload == capability_payload
    assert result.load_exchange == load_exchange


def test_unreachable_preserves_method_not_found_payload() -> None:
    """Catches a classifier that loses the exact live rejection needed for review."""
    capability_payload = {"loadSession": False, "sessionCapabilities": {}}
    load_exchange = {
        "request": {"jsonrpc": "2.0", "id": 7, "method": "session/load", "params": {"sessionId": "saved-1"}},
        "response": {"jsonrpc": "2.0", "id": 7, "error": {"code": -32601, "message": "Method not found"}},
    }

    result = evaluate_session_load_exchange(capability_payload, load_exchange)

    assert result.finding is Finding.UNREACHABLE
    assert result.load_exchange["response"]["error"] == {"code": -32601, "message": "Method not found"}


def test_incomplete_exchange_is_indeterminate_even_when_advertised() -> None:
    """Catches a claim based solely on initialize when acpx did not invoke load."""
    capability_payload = {"loadSession": True, "sessionCapabilities": {}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.INDETERMINATE
    assert result.load_exchange is None


def test_unadvertised_live_load_capability_is_unreachable_without_a_forced_call() -> None:
    """Catches treating acpx's capability-gated non-call as an incomplete observation."""
    capability_payload = {"sessionCapabilities": {"resume": False}}

    result = evaluate_session_load_exchange(capability_payload, None)

    assert result.finding is Finding.UNREACHABLE
    assert result.capability_payload == capability_payload
    assert result.load_exchange is None


def test_acpx_exported_session_capabilities_are_retained_as_live_evidence(tmp_path: Path) -> None:
    """Catches losing the initialized capabilities that acpx itself persisted."""
    archive = tmp_path / "session.json"
    archive.write_text(
        json.dumps(
            {
                "session": {
                    "state": {
                        "agent_capabilities": {"loadSession": False, "sessionCapabilities": {"resume": False}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    assert extract_acpx_archive_capability_payload(archive) == {
        "loadSession": False,
        "sessionCapabilities": {"resume": False},
    }


def test_raw_acpx_agent_command_uses_slash_normalized_windows_paths() -> None:
    """Catches acpx treating Windows backslashes in a raw agent command as escapes."""
    command = build_acpx_command(
        Path(r"C:\Tools\acpx.cmd"),
        workspace=Path(r"C:\probe workspace"),
        agent=Path(r"D:\agent path\optimus-agent.exe"),
    )

    assert command[-2] == "--agent"
    assert command[-1] == '"D:/agent path/optimus-agent.exe" --workspace-root "C:/probe workspace" --no-auto-start'


def test_temporary_workspace_approval_uses_the_trust_cli_and_has_a_matching_revoke() -> None:
    """Catches a live probe that could create approval state without its paired cleanup command."""
    workspace = Path(r"C:\probe workspace")

    approve = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "approve")
    revoke = build_trust_command(Path(r"C:\Tools\optimus-trust.exe"), workspace, "revoke")

    assert approve[-3:] == ["approve", "--mode", "durable"]
    assert revoke[-1:] == ["revoke"]
    assert approve[:3] == [r"C:\Tools\optimus-trust.exe", "--workspace-root", r"C:\probe workspace"]
    assert approve[:3] == revoke[:3]


def test_acpx_evidence_keeps_protocol_records_but_redacts_secret_aliases_and_free_text() -> None:
    """Catches unsafe persistence of tool streams from the independently authored client."""
    result = CommandResult(
        command=["acpx", "sessions", "new"],
        returncode=1,
        stdout=(
            '{"jsonrpc":"2.0","result":{"agentCapabilities":'
            '{"loadSession":false,"apiKey":"json-secret","credential":"credential-secret"}}}'
        ),
        stderr="OPTIMUS_API_KEY=env-secret Bearer bearer-secret",
    )

    evidence = capture_acpx_evidence(result)

    serialized = json.dumps(evidence)
    assert "json-secret" not in serialized
    assert "credential-secret" not in serialized
    assert "env-secret" not in serialized
    assert "bearer-secret" not in serialized
    assert evidence["capability_payload"] == {
        "loadSession": False,
        "apiKey": "**********",
        "credential": "**********",
    }


def test_cleanup_remediation_is_workspace_scoped_and_contains_no_approval_identifier() -> None:
    """Catches a cleanup-failure path that cannot tell the operator exactly what to undo."""
    remediation = build_cleanup_remediation(
        Path(r"C:\Tools\optimus-trust.exe"), Path(r"C:\probe workspace")
    )

    assert str(remediation[0]).endswith("optimus-trust.exe")
    assert remediation[1:4] == ["--workspace-root", r"C:\probe workspace", "revoke"]
    assert all("approval" not in part.casefold() for part in remediation)


def test_redis_startup_failure_is_a_precondition_with_the_runbook_remediation() -> None:
    """Catches treating a missing Redis dependency as an observation about Zed."""
    context = classify_indeterminate_context(
        {
            "stderr": "optimus-agent: Redis is not reachable. Start Redis or fix OPTIMUS_REDIS_URL."
        }
    )

    assert context["indeterminate_reason"] == "PRECONDITION_UNMET"
    assert context["precondition"] == {
        "name": "redis",
        "remediation": {
            "runbook": "docs/runbooks/local-live-dependencies.md#5-bounded-session-bound-smoke-redis--gateway-optional-phoenix",
            "command": "optimus-agent --workspace-root <throwaway-workspace> --check-config --strict",
        },
    }


def test_missing_load_exchange_is_an_incomplete_observation_not_a_precondition() -> None:
    """Catches collapsing a clean ACP exchange gap into an infrastructure to-do."""
    context = classify_indeterminate_context({"stderr": "", "stdout_records": []})

    assert context == {"indeterminate_reason": "OBSERVATION_INCOMPLETE", "precondition": None}
