"""#583: a model-authored path holding a control, format or surrogate character, or longer than MAX_PATH_CHARS, is
rejected at parse time with a fixed message, so it never reaches the person's text or the model's next-turn history."""

from __future__ import annotations

import unicodedata
from decimal import Decimal
from typing import Any

import pytest

from optimus.agent.directives import MAX_PATH_CHARS, AgentDirectiveParseError, parse_agent_plan
from optimus.agent.planning_loop import PlanningTurnKind, PlanningTurnParseError, parse_planning_turn
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from tests.unit.acp.test_hidden_text_stops_end_turn import drive_stop_turn

UNSAFE = {
    "esc": "src/a\x1b[31mb.py",
    "nul": "src/a\x00b.py",
    "rlo": "src/a‮yp.exe",
    "zwsp": "src/a​b.py",
    "c1-csi": "src/a\x9b31mb.py",
    "del": "src/a\x7fb.py",
    "too-long": "d/" * (MAX_PATH_CHARS // 2) + "x.py",
}
ACCEPTED = ("src/café.py", "docs/日本語.md", "pkg/naïve-file_v1.2.py", "d/" * (MAX_PATH_CHARS // 2 - 2) + "x.py")


def _plan(directive: str, path: str) -> str:
    if directive == "READ":
        return f"READ {path}\n"
    if directive == "WRITE":
        return f"WRITE {path}\ncontent\n"
    return f"EDIT {path}\n<<<<<<< OLD\nold\n======= NEW\nnew\n>>>>>>> END\n"


def _unsafe_characters(text: str) -> list[str]:
    return [hex(ord(c)) for c in text if c not in "\n\r\t" and unicodedata.category(c) in {"Cc", "Cf", "Cs"}]


@pytest.mark.parametrize("path", UNSAFE.values(), ids=UNSAFE.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_an_unsafe_path_is_rejected_with_a_fixed_message(directive, path):
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert str(caught.value) == "no valid agent directives"
    # The planner sees no final plan: the turn is unparseable, and its fixed notice quotes nothing.
    with pytest.raises(PlanningTurnParseError) as turn:
        parse_planning_turn(_plan(directive, path))
    assert turn.value.code == "GRAMMAR_UNRECOGNIZED" and path not in str(turn.value)


@pytest.mark.parametrize("path", UNSAFE.values(), ids=UNSAFE.keys())
def test_an_unsafe_ranged_read_path_is_rejected_with_a_fixed_message(path):
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"OBSERVE: the header\nREAD: {path}#bytes=0:10\n")

    assert caught.value.code == "READ_PATH_NOT_RELATIVE"
    assert str(caught.value) == "READ path must be workspace-relative"


@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_c1_next_line_is_never_a_path(directive):
    """U+0085 is a content separator (#410 R1): its line is not a directive at all, so it is rejected before the path rule."""
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(_plan(directive, "src/a\x85b.py"), edit_base="forbidden")
    assert "\x85" not in str(caught.value)


@pytest.mark.parametrize("path", ACCEPTED, ids=["latin", "cjk", "dots-dashes", "at-bound"])
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_legitimate_path_is_still_accepted(directive, path):
    assert len(path) <= MAX_PATH_CHARS
    plan = parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert (plan.read_paths[0] if directive == "READ" else plan.write.path) == path
    ranged = parse_planning_turn(f"OBSERVE: the header\nREAD: {path}#bytes=0:10\n")
    assert ranged.kind is PlanningTurnKind.READ_MORE and ranged.read_requests[0].path == path


class _SamePlan:
    """Every planning turn returns ``plan``; records what the model was sent."""

    def __init__(self, plan: str) -> None:
        self._plan, self.calls = plan, []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, metadata
        self.calls.append(input_text)
        request_id = f"gw-{len(self.calls)}"
        usage = GatewayUsage(gateway_request_id=request_id, provider="glm", billing_units=1, cost_usd=Decimal("0.001"))
        return GatewayResponse(response_id=request_id, output_text=self._plan, gateway_usage=usage, raw={"id": request_id})


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list | tuple):
        return [s for item in value for s in _strings(item)]
    return []


async def test_an_edit_whose_path_reorders_text_reaches_neither_the_person_nor_the_history(tmp_path):
    """The original symptom: EDIT src/app<U+202E>yp.exe used to be quoted in the EDIT failure text. Now the plan never
    parses, the run stops with its fixed text, and no text the person or the next turn's model reads carries it."""
    (tmp_path / "small.py").write_text("old\n")
    gateway = _SamePlan(_plan("EDIT", "small‮yp.py"))

    def produce(request):
        return AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore()).run(request)

    result, updates, _, records = await drive_stop_turn(tmp_path, produce, approve=False)

    [record] = records.values()
    assert _unsafe_characters(record.completion_text) == []
    assert [s for s in _strings(updates) if _unsafe_characters(s)] == []
    assert len(gateway.calls) > 1 and [call for call in gateway.calls[1:] if "‮" in call] == []
    assert result["_meta"]["runStopReason"] == "PLANNING_UNPARSEABLE_RESPONSE"
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]
    assert "did not match the required directive grammar" in final
