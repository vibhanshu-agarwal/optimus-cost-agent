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
    evaluate_session_load_exchange,
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
