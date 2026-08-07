"""P11-FU-9 Task 8 ACP-protocol evidence via independent ``acpx``.

Requires real ``acpx`` and a real agent process. Never uses a project-authored
ACP client. Skipped runs are not evidence for DoD claims.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.run_p11_fu_9_acpx_evidence import (
    AcpxNotFoundError,
    assert_scratch_paths_ignored,
    build_evidence_summary,
    extract_safe_evidence,
    parse_jsonl_records,
    resolve_acpx,
    resolve_optimus_agent,
    run_capture,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = [pytest.mark.e2e, pytest.mark.requires_acpx]


def _require_acpx() -> tuple[str, str]:
    try:
        path = resolve_acpx()
    except AcpxNotFoundError as exc:
        pytest.skip(str(exc))
    from tools.run_p11_fu_9_acpx_evidence import acpx_version

    try:
        version = acpx_version(path)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"acpx_version_unavailable: {exc}")
    return path, version


def _require_agent() -> str:
    try:
        return resolve_optimus_agent()
    except AcpxNotFoundError as exc:
        pytest.skip(str(exc))


def test_scratch_ignore_rules_are_in_force_before_acpx_capture() -> None:
    # Unit-tier-safe: does not require a live agent session.
    assert_scratch_paths_ignored(repo_root=REPO_ROOT)


def test_empty_mcp_servers_array_is_exact_noop_via_acpx(tmp_path: Path) -> None:
    acpx_path, _version = _require_acpx()
    agent = _require_agent()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    md_report = tmp_path / "evidence.md"
    json_report = tmp_path / "evidence.json"

    try:
        exit_code = run_capture(
            scratch_dir=scratch,
            repo_root=REPO_ROOT,
            task="Reply with exactly: p11-fu-9-empty-mcp-ok",
            mcp_servers=[],
            md_report=md_report,
            json_report=json_report,
            agent_argv=[agent.replace("\\", "/"), "--workspace-root", str(scratch)],
            timeout=120.0,
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"acpx_capture_unavailable: {type(exc).__name__}: {exc}")

    if not json_report.is_file():
        pytest.skip("acpx_evidence_report_missing")

    summary = json.loads(json_report.read_text(encoding="utf-8"))
    assert summary["empty_mcp_servers_noop"] is True
    assert summary["acpx_client"].startswith("external")
    assert summary["mcp_capabilities"]["http"] is False
    assert summary["mcp_capabilities"]["sse"] is False
    # Capture may fail for gateway/env reasons; that is a skip, not fabricated success.
    if not summary.get("capture_complete"):
        pytest.skip(
            f"acpx_capture_incomplete exit={exit_code} stop={summary.get('stop_reason')!r}"
        )
    assert summary.get("session_id")
    assert summary.get("stop_reason")


def test_extract_safe_evidence_from_fixture_transcript_does_not_require_live_acpx() -> None:
    """Harness verifier path remains unit-exercisable without live deps."""
    transcript = "\n".join(
        [
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 0,
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {"mcpCapabilities": {"http": False, "sse": False}},
                    },
                }
            ),
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"sessionId": "session-fixture"}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"stopReason": "end_turn"}}),
        ]
    )
    records = parse_jsonl_records(transcript)
    evidence = extract_safe_evidence(
        records,
        acpx_path=shutil.which("acpx") or "/usr/bin/acpx",
        acpx_version="0.12.0",
        exit_code=0,
    )
    summary = build_evidence_summary(evidence=evidence, mcp_servers_count=0, capture_complete=True)
    assert summary["empty_mcp_servers_noop"] is True
    assert summary["session_id"] == "session-fixture"
