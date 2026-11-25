"""Plan 12.14 Task 3 (D4) through the real memory turn and the runner: only a Chat turn's own task may ask for the overflow outline; the
outline comes from this turn's read (unsaved text included), is disclosed in the pack and recorded body-free; Agent keeps its ranged reads.
Files, the file policy and the turn are real; the storage port answers from a table, as in test_memory_tools_and_turns."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from context_engine.file_outline import DISCLOSURE, OUTLINE_VERSION
from optimus.agent.models import AgentRunRequest
from optimus.agent.runner import AgentRunner
from optimus.agent.workspace_context import WorkspaceContextResult
from optimus.context.context_budget import BudgetPolicy
from optimus.runtime.modes import ExecutionMode
from tests.unit.context.test_memory_tools_and_turns import _session, _Storage, workspace  # noqa: F401 - fixture

BODY = "BODY_ONLY_TEXT_NEVER_IN_AN_OUTLINE"
BIG = "".join(f"def handler_{i}(event, context):\n    return '{BODY} {i}'\n\n\n" for i in range(400))
TASK = 'Summarize "pkg/big.py"'
AWARE = BudgetPolicy("model-aware", 3_000, 1_500)


def _assemble(turn, *, task: str = TASK, overview: str | None = "pkg/big.py", budget: BudgetPolicy | None = AWARE):
    return turn.assemble(run_id="run-1", task=task, selection_text=task, model_id="m", estimate=len, usable_input_tokens=40_000, pack_budget=budget,
                         overview_path=overview)


@pytest.fixture
def big(workspace):  # noqa: F811
    (workspace / "pkg" / "big.py").write_text(BIG, encoding="utf-8", newline="\n")
    return workspace


def test_a_chat_summary_of_a_file_over_the_ceiling_gets_a_disclosed_outline_recorded_body_free(big):
    turn = _session(big, _Storage()).turn()
    result = _assemble(turn)
    assert result.blocking_stop_reason is None and DISCLOSURE in result.text and BODY not in result.text
    assert "--- pkg/big.py (outline: 400 entries) ---" in result.text and result.file_sha256s["pkg/big.py"] == hashlib.sha256(BIG.encode()).hexdigest()
    outline = turn.manifest["outline"]
    assert outline is not None, "the manifest records the outline's metadata"
    assert (outline["path"], outline["generator"], outline["reread_required"]) == ("pkg/big.py", OUTLINE_VERSION, True)
    assert turn.manifest["selected"][0]["disclosure"] == "outline"
    recorded = json.dumps(turn.manifest)
    assert BODY not in recorded and "def handler_0" not in recorded, "the manifest keeps ranges and hashes, never the outline's text"


def test_the_outline_is_built_from_this_turns_unsaved_text(big):
    turn = _session(big, _Storage()).turn()
    edited = BIG.replace("def handler_0(event, context):", "def renamed_entry(event):")
    turn.read_buffer = lambda path: edited if path.endswith("big.py") else None
    result = _assemble(turn)
    assert "1-2 def renamed_entry(event)" in result.text and turn.manifest["unsaved_buffers"] == ["pkg/big.py"]
    assert turn.manifest["outline"]["source_sha256"] == hashlib.sha256(edited.encode()).hexdigest()


@pytest.mark.parametrize(("task", "overview", "budget"), [
    ('Summarize "pkg/big.py" and rename handler_3', None, AWARE),  # the runner names no target for any other task
    (TASK, None, AWARE),  # an Agent turn: no target, so its ranged reads of the file go on as before
    (TASK, "pkg/big.py", None),  # the legacy budget: M2a's refusal
])
def test_without_a_target_and_a_model_aware_budget_the_file_is_too_large_as_before(big, task, overview, budget):
    result = _assemble(_session(big, _Storage()).turn(), task=task, overview=overview, budget=budget)
    assert result.blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE" and BODY not in result.text


def test_a_small_file_asked_for_by_a_summary_is_sent_whole(workspace):  # noqa: F811
    turn = _session(workspace, _Storage()).turn()
    result = _assemble(turn, task='Summarize "pkg/a.py"', overview="pkg/a.py")
    assert "return 'needle here'" in result.text and DISCLOSURE not in result.text and turn.manifest["outline"] is None


@pytest.mark.parametrize(("mode", "task", "expected"), [
    (ExecutionMode.CHAT, TASK, "pkg/big.py"),
    (ExecutionMode.CHAT, 'Summarize "pkg/big.py" then fix it', None),
    (ExecutionMode.AGENT, TASK, None),
])
def test_the_runner_names_a_target_only_for_a_chat_turns_own_summary_task(tmp_path, mode, task, expected):
    seen: dict = {}

    class Memory:
        def assemble(self, **kwargs):
            seen.update(kwargs)
            return WorkspaceContextResult(text="", max_total_bytes=16_384, used_bytes=0, prioritized_paths=(), omitted_paths=(), diagnostics=())

    packer = type("Packer", (), {"memory": Memory(), "model_id": "m", "estimate_request": staticmethod(len), "usable_input_tokens": 229_376, "pack_budget": AWARE})()
    request = AgentRunRequest(run_id="r", task=task, execution_mode=mode, workspace_root=tmp_path, max_cost_usd=Decimal("0"))
    AgentRunner(gateway_client=object(), model="m")._turn_context(request, f"earlier: Summarize \"other.py\"\n{task}", packer)  # noqa: SLF001
    assert seen["overview_path"] == expected, "only the turn's own task counts, never the selection text's history"
