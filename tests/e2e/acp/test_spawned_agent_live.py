from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest

from optimus.acp.e2e_transcript import PLAN_9_6_E2E_TRANSCRIPT_PATH, E2eAcpTranscriptWriter
from optimus.acp.operator_verify import OperatorLiveSessionConfig, ensure_verify_workspace, run_operator_live_session
from optimus.acp.preflight import PreflightFailure, run_preflight
from tests.integration.optimus_gateway.gateway_env import project_root

pytestmark = pytest.mark.e2e

_DEFAULT_LIVE_MAX_COST_USD = Decimal("0.25")
_LIVE_MODEL = "claude-haiku"
_DOCSTRING_TASK = (
    "Add a module docstring to `example.py` describing its function. "
    "Modify only `example.py`; do not create any other files or tests."
)


def _live_max_cost_usd() -> Decimal:
    raw = os.environ.get("OPTIMUS_LIVE_MAX_COST_USD", "").strip()
    if not raw:
        return _DEFAULT_LIVE_MAX_COST_USD
    return Decimal(raw)


def _assert_cost_within_cap(cost_usd: Decimal) -> None:
    cap = _live_max_cost_usd()
    assert cost_usd <= cap, f"live e2e cost {cost_usd} exceeded OPTIMUS_LIVE_MAX_COST_USD cap {cap}"


def test_spawned_acp_agent_live_docstring_turn(tmp_path: Path) -> None:
    workspace = tmp_path.resolve()
    try:
        run_preflight(os.environ, workspace_root=workspace, strict=True, require_timeseries=True)
    except PreflightFailure as exc:
        pytest.fail(exc.user_message)

    ensure_verify_workspace(workspace)
    example = workspace / "example.py"
    original_text = example.read_text(encoding="utf-8")
    transcript = E2eAcpTranscriptWriter()
    config = OperatorLiveSessionConfig(
        workspace_root=workspace,
        project_root=project_root(),
        model=_LIVE_MODEL,
        task=_DOCSTRING_TASK,
        transcript_path=PLAN_9_6_E2E_TRANSCRIPT_PATH,
    )

    try:
        result = run_operator_live_session(config, environ=os.environ, transcript=transcript)
        assert result.success, result.failure_message
        assert result.stop_reason == "end_turn"

        updated_text = example.read_text(encoding="utf-8")
        assert updated_text != original_text, "example.py was not modified by the spawned agent"
        assert '"""' in updated_text or "'''" in updated_text, f"expected a docstring in example.py:\n{updated_text}"
        assert "def greet" in updated_text, f"expected original greet() to be preserved in example.py:\n{updated_text}"
        assert "return 'hello'" in updated_text, f"expected greet body to be preserved in example.py:\n{updated_text}"

        assert result.total_cost_usd > Decimal("0")
        _assert_cost_within_cap(result.total_cost_usd)
    except Exception:
        transcript.write(PLAN_9_6_E2E_TRANSCRIPT_PATH)
        raise
    finally:
        transcript.write(PLAN_9_6_E2E_TRANSCRIPT_PATH)
