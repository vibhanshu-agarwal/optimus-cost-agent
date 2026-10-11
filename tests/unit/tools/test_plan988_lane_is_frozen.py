"""Plan 12.2 Task 11 changed the multi-turn planner prompt, which the Plan 9.88 FU-4B lane had frozen at fu5a.

The lane's historical evidence stays verifiable against its own prompt version (the bridged claims in
`test_verify_plan987_acpx_evidence.py`), a Plan 9.87 claim still needs the current prompt, and the lane
runner captures no new attempt under a label its prompt no longer matches.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from optimus.agent.prompts import MULTI_TURN_PLANNER_PROMPT_VERSION  # noqa: E402
from tools import run_plan987_acpx_live_evidence as plan987  # noqa: E402
from tools import run_plan988_fu4b_live_evidence as plan988  # noqa: E402


def test_the_product_prompt_has_left_the_frozen_lane() -> None:
    assert MULTI_TURN_PLANNER_PROMPT_VERSION != plan988.LANE_PROMPT_VERSION
    assert plan987.PROMPT_VERSION == MULTI_TURN_PLANNER_PROMPT_VERSION


def test_a_plan987_claim_still_requires_the_current_prompt() -> None:
    summary = {"schema_version": plan987.EVIDENCE_SCHEMA_VERSION, "session_id": "s", "run_id": "r", "prompt_version": plan988.LANE_PROMPT_VERSION}
    with pytest.raises(ValueError, match="prompt_version mismatch"):
        plan987._check_common_summary(summary, "")
    with pytest.raises(ValueError, match="usage_recorded"):  # the lane's own version passes this requirement
        plan987._check_common_summary(summary, "", prompt_version=plan988.LANE_PROMPT_VERSION)


@pytest.mark.parametrize("mode", ["--pre-register", "--run"])
def test_the_frozen_lane_captures_no_new_attempt(tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str) -> None:
    workspace, report = tmp_path / "ws", tmp_path / "report.md"
    argv = [mode, "--attempt", "1", "--implementation-sha", "0" * 40, "--report", str(report), "--workspace", str(workspace)]

    assert plan988.main(argv) == 2
    assert "frozen" in capsys.readouterr().err
    assert not workspace.exists() and not report.exists()
