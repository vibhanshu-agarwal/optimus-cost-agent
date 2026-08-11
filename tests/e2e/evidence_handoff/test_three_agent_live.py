"""Real three-agent live contract (Task 10).

This module must not be made green by a project-authored agent harness, MCP
emulator, or scenario-shape fixture alone. Live bodies are gated by
``requires_real_agents``; shape/boundary checks fail until the verifier exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCENARIO_FIXTURE = (
    REPO_ROOT / "tests" / "fixtures" / "evidence_handoff" / "three_agent_scenario.json"
)
VERIFIER_MODULE = "tools.verify_evidence_handoff_live"


def _import_verifier():
    return __import__(VERIFIER_MODULE, fromlist=["*"])


def test_three_agent_scenario_fixture_exists_as_shape_only() -> None:
    assert SCENARIO_FIXTURE.is_file()
    scenario = json.loads(SCENARIO_FIXTURE.read_text(encoding="utf-8"))
    assert scenario["purpose"] == "scenario_shape_only"
    assert scenario["pass_forbidden_without_real_evidence"] is True
    # Verifier must exist and refuse this fixture as a live evidence root.
    verifier = _import_verifier()
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=SCENARIO_FIXTURE.parent.resolve(),
            service_endpoint="http://127.0.0.1:8765/mcp",
            expected_agent_ids=tuple(row["agent_id"] for row in scenario["agents"]),
        )
    assert raised.value.code in {
        "scenario_shape_insufficient",
        "missing_manifest_field",
        "evidence_incomplete",
    }


def test_verifier_refuses_implicit_roots_and_defaults() -> None:
    verifier = _import_verifier()
    with pytest.raises(verifier.VerificationError) as raised:
        verifier.verify_evidence(
            evidence_root=None,
            service_endpoint=None,
            expected_agent_ids=("a", "b", "c"),
        )
    assert raised.value.code in {
        "missing_evidence_root",
        "missing_service_endpoint",
    }


@pytest.mark.requires_real_agents
def test_three_agent_live_evidence_against_real_native_clients() -> None:
    """Operator-provisioned Claude Code / Codex / Cursor evidence only.

    A skipped agent, fake client, simulated warning, or project-authored
    ACP/MCP driver is not a pass (plan Task 10 Step 3).
    """
    verifier = _import_verifier()
    # Explicit roots must be supplied by the operator environment; never default.
    evidence_root = Path(
        __import__("os").environ["EVIDENCE_HANDOFF_LIVE_EVIDENCE_ROOT"]
    )
    service_endpoint = __import__("os").environ["EVIDENCE_HANDOFF_LIVE_SERVICE_ENDPOINT"]
    assert evidence_root.is_absolute()
    assert service_endpoint.startswith("http")
    result = verifier.verify_evidence(
        evidence_root=evidence_root,
        service_endpoint=service_endpoint,
        expected_agent_ids=(
            __import__("os").environ["EVIDENCE_HANDOFF_LIVE_AGENT_CLAUDE"],
            __import__("os").environ["EVIDENCE_HANDOFF_LIVE_AGENT_CURSOR"],
            __import__("os").environ["EVIDENCE_HANDOFF_LIVE_AGENT_CODEX"],
        ),
    )
    assert result["passed"] is True
    assert set(result["client_names"]) == {"claude_code", "cursor", "codex"}
    assert result["implementer_append_rejected"] is True
    assert result["sequence_unchanged_on_implementer_reject"] is True
    assert result["post_latch_warnings"] == {
        "claude_code": "ledger_integrity_failed",
        "cursor": "ledger_integrity_failed",
        "codex": "ledger_integrity_failed",
    }
    assert result["automatic_relay"] is False
