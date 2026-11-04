"""Plan 12.10 Task 4: the four tools, a turn's context and Chat's search rounds. Files, the file policy, the guard, the parser and the real
runner are real; the storage port answers from a table and the Gateway is scripted, so each decision is isolated. The route itself is
proved against real Redis in tests/integration/context."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from context_engine.code_index import path_id
from context_engine.retrieval import Hit, Retriever
from optimus.agent.directives import IndexToolRequest, parse_index_tool_reply
from optimus.agent.index_turn import MAX_INDEX_ROUNDS, keep_newest, run_index_tools
from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.prompts import build_agent_planner_input, build_indexed_chat_input, build_multi_turn_planner_input
from optimus.agent.runner import AgentRunner
from optimus.agent.tools import AgentToolbox
from optimus.context.index_tools import IndexTools
from optimus.context.memory_session import GroundingReport, MemorySession, named_symbols
from optimus.context.project_registry import ProjectRegistration
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails.file_policy import FilePolicy, FilePurpose
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import RuntimeContext

SOURCE = "class Parser:\n    def parse(self, text):\n        return text\n\n\ndef helper():\n    return 'needle here'\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _record(ident: str, path: str, symbol: str | None, file_hash: str, *, kind: str = "symbol", lines=(1, 3), signature: str | None = None) -> dict:
    record = {"id": ident, "kind": kind, "path": path, "path_id": path_id(path), "file_hash": file_hash, "language": "python", "start_line": lines[0], "end_line": lines[1]}
    if symbol:
        record["symbol"] = symbol
    if signature:
        record["signature"] = signature
    return record


class _Storage:
    def __init__(self, records=(), *, complete=True, current=True):
        self.records = list(records)
        self.complete = complete
        self.current = current
        self.calls: list[tuple[str, dict]] = []

    def call(self, op, **fields):
        self.calls.append((op, fields))
        if op == "coverage":
            if not self.current:
                return {"current": None}
            return {"current": {"epoch": 3, "revision": "r" * 64, "coverage": {"complete": self.complete, "files_indexed": 2, "files_total": 2 if self.complete else 9, "unsupported": 0}}}
        if op == "catalogue":
            return {"files": [{"path": record["path"], "file_hash": record["file_hash"], "language": "python", "modified": None, "description": None} for record in self.records], "cursor": None}
        if fields.get("mode") == "symbol":
            return {"records": [record for record in self.records if record.get("symbol") == fields["symbol"]]}
        if fields.get("mode") == "path":
            return {"records": [record for record in self.records if record["path_id"] == fields["path_id"]][: fields["k"]]}
        return {"records": list(self.records)}


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text(SOURCE, encoding="utf-8", newline="\n")
    (tmp_path / "notes.md").write_text("# Title\n\nSome prose.\n", encoding="utf-8", newline="\n")
    (tmp_path / ".env").write_text("TOKEN=hunter2\n", encoding="utf-8")
    return tmp_path


def _tools(workspace: Path, storage: _Storage, *, listing=None, **kwargs) -> IndexTools:
    policy = FilePolicy(workspace)

    def read(path: str) -> bytes | None:
        decision, data = policy.read(path, purpose=FilePurpose.AUTOMATIC)
        return data if decision.allowed else None

    listed = listing if listing is not None else [decision.relative_path for decision in policy.walk(purpose=FilePurpose.AUTOMATIC) if decision.allowed]
    return IndexTools(retriever=Retriever(storage, None), storage=storage, read=read, listing=lambda: listed, **kwargs)


# --- the grammar ----------------------------------------------------------------------------------


def test_a_whole_reply_of_tool_lines_is_a_request():
    assert parse_index_tool_reply('SEARCH parse the text\nOUTLINE pkg/a.py\nSYMBOLS Parser.parse\nLIST .') == (
        IndexToolRequest("SEARCH", "parse the text"), IndexToolRequest("OUTLINE", "pkg/a.py"), IndexToolRequest("SYMBOLS", "Parser.parse"), IndexToolRequest("LIST", "."))
    assert parse_index_tool_reply("```\nLIST pkg\n```") == (IndexToolRequest("LIST", "pkg"),)


@pytest.mark.parametrize("reply", [
    "The answer is that you can SEARCH the code.",
    "SEARCH one\nand then some prose",
    "Here it is:\nLIST pkg",
    "LIST of things to check",
    "OUTLINE two words",
    "READ pkg/a.py",
    "WRITE a.py\nx",
    "SEARCH a\nSEARCH b\nSEARCH c\nSEARCH d\nSEARCH e",
    "",
])
def test_anything_else_is_not_a_request(reply):
    assert parse_index_tool_reply(reply) is None


# --- the tools ------------------------------------------------------------------------------------


def test_search_shows_current_results_and_states_its_scope(workspace):
    file_hash = _sha(SOURCE)
    text = _tools(workspace, _Storage([_record("x", "pkg/a.py", "Parser", file_hash, signature="class Parser:")], complete=False)).run("SEARCH", "parser")
    assert "pkg/a.py:1-3 Parser: class Parser:" in text
    assert "index generation 3, still building, 2 of 9 files" in text and "covers only this scope" in text


def test_search_drops_a_record_whose_file_changed_and_never_shows_its_signature(workspace):
    text = _tools(workspace, _Storage([_record("x", "pkg/a.py", "Gone", _sha("older"), signature="def old_name():")])).run("SEARCH", "gone")
    assert "old_name" not in text and "No matches in this scope." in text
    assert "1 indexed results were left out because their files changed" in text


def test_search_drops_a_record_the_file_policy_now_refuses(workspace):
    text = _tools(workspace, _Storage([_record("x", ".env", "TOKEN", _sha("TOKEN=hunter2\n"), signature="TOKEN=hunter2")])).run("SEARCH", "token")
    assert "hunter2" not in text


def test_with_no_index_search_says_it_knows_nothing_rather_than_no_matches(workspace):
    text = _tools(workspace, _Storage(current=False)).run("SEARCH", "x")
    assert "could not answer (unpublished)" in text and "No matches" not in text


def test_a_quoted_search_reads_disk_and_says_what_it_read(workspace):
    text = _tools(workspace, _Storage(current=False)).run("SEARCH", '"needle here"')
    assert "pkg/a.py:7:" in text and "needle here" in text
    assert "read 2 of 2 admitted files from disk." in text


def test_a_quoted_search_never_reads_a_denied_file(workspace):
    assert "hunter2" not in _tools(workspace, _Storage()).run("SEARCH", '"TOKEN"')


def test_a_quoted_search_stops_at_its_time_limit_and_says_so(workspace):
    times = iter([0.0, 0.0, 100.0, 100.0, 100.0])
    text = _tools(workspace, _Storage(), clock=lambda: next(times)).run("SEARCH", '"needle here"')
    assert "stopped by the time limit" in text


def test_a_cancel_stops_a_quoted_search(workspace):
    text = _tools(workspace, _Storage(), cancelled=lambda: True).run("SEARCH", '"needle here"')
    assert "read 0 of 2" in text and "stopped by the turn was cancelled" in text


def test_outline_reads_the_file_now_so_it_needs_no_index(workspace):
    text = _tools(workspace, _Storage(current=False)).run("OUTLINE", "pkg/a.py")
    assert "read from disk now" in text and "Parser.parse" in text and "helper" in text


def test_outline_refuses_a_denied_file_without_opening_it(workspace):
    text = _tools(workspace, _Storage()).run("OUTLINE", ".env")
    assert "cannot be read" in text and "hunter2" not in text


def test_symbols_finds_the_exact_name_and_drops_a_stale_one(workspace):
    fresh = _record("x", "pkg/a.py", "Parser.parse", _sha(SOURCE), signature="def parse(self, text):")
    stale = _record("y", "notes.md", "Parser.parse", _sha("older"))
    text = _tools(workspace, _Storage([fresh, stale])).run("SYMBOLS", "Parser.parse")
    assert "pkg/a.py:1-3 Parser.parse: def parse(self, text):" in text
    assert "results were left out because their files changed" in text


def test_list_shows_only_what_the_policy_admits(workspace):
    text = _tools(workspace, _Storage()).run("LIST", ".")
    assert "pkg/ (1 files)" in text and "notes.md" in text and ".env" not in text
    assert "a.py" in _tools(workspace, _Storage()).run("LIST", "pkg")
    assert "Nothing the file policy admits" in _tools(workspace, _Storage()).run("LIST", "absent")


def test_a_result_is_bounded_in_bytes(workspace):
    many = [f"pkg/file{i}.py" for i in range(5000)]
    text = _tools(workspace, _Storage(), listing=many).run("LIST", "pkg")
    assert len(text.encode("utf-8")) <= 8 * 1024


# --- running them in a turn -----------------------------------------------------------------------


def _toolbox(workspace: Path, mode: ExecutionMode = ExecutionMode.CHAT) -> AgentToolbox:
    return AgentToolbox.for_workspace(workspace_root=workspace, context=RuntimeContext(execution_mode=mode), run_id="run", session_id="s")


def _memory(tools) -> SimpleNamespace:
    return SimpleNamespace(tools=tools, on_tool=None, seen_requests=set())


@pytest.mark.parametrize("mode", [ExecutionMode.CHAT, ExecutionMode.AGENT])
def test_every_tool_passes_the_guard_in_both_modes(workspace, mode):
    memory = _memory(_tools(workspace, _Storage()))
    requests = (IndexToolRequest("SEARCH", "x"), IndexToolRequest("OUTLINE", "pkg/a.py"), IndexToolRequest("SYMBOLS", "x"), IndexToolRequest("LIST", "."))
    ran = run_index_tools(requests, memory, _toolbox(workspace, mode))
    assert [call.authorization_outcome for call in ran.calls] == ["ALLOW"] * 4
    assert [call.tool_name for call in ran.calls] == ["index_search", "index_outline", "index_symbols", "index_list"]


@pytest.mark.parametrize("argument", ["../outside.py", "..\\outside.py"])
def test_the_guard_refuses_a_path_outside_the_workspace(workspace, argument):
    ran = run_index_tools((IndexToolRequest("OUTLINE", argument),), _memory(_tools(workspace, _Storage())), _toolbox(workspace))
    assert ran.calls[0].authorization_outcome == "BLOCK"
    assert "Refused:" in ran.envelope


def test_a_repeat_is_not_run_again_and_a_reply_of_only_repeats_is_no_progress(workspace):
    storage = _Storage()
    memory = _memory(_tools(workspace, storage))
    first = run_index_tools((IndexToolRequest("SEARCH", "x"),), memory, _toolbox(workspace))
    asked = len(storage.calls)
    second = run_index_tools((IndexToolRequest("SEARCH", "x"),), memory, _toolbox(workspace))
    assert first.novel and not second.novel and second.calls == ()
    assert len(storage.calls) == asked and "already answered" in second.envelope


def test_each_tool_gets_a_started_and_an_ended_card(workspace):
    cards = []
    memory = _memory(_tools(workspace, _Storage()))
    memory.on_tool = lambda phase, tool, argument, summary: cards.append((phase, tool, argument))
    run_index_tools((IndexToolRequest("LIST", "."), IndexToolRequest("OUTLINE", "../x")), memory, _toolbox(workspace))
    assert cards == [("started", "LIST", "."), ("completed", "LIST", "."), ("started", "OUTLINE", "../x"), ("failed", "OUTLINE", "../x")]


def test_a_cancel_stops_further_tools(workspace):
    ran = run_index_tools((IndexToolRequest("LIST", "."),), _memory(_tools(workspace, _Storage())), _toolbox(workspace), halted=lambda: True)
    assert ran.calls == () and ran.envelope == ""


def test_evidence_keeps_the_newest_whole_blocks():
    blocks = "".join(f"INDEX_TOOL LIST {i}\n{'x' * 4000}\nEND_INDEX_TOOL\n" for i in range(20))
    kept = keep_newest(blocks)
    assert len(kept.encode("utf-8")) <= 32 * 1024
    assert kept.startswith("INDEX_TOOL LIST ") and kept.rstrip().endswith("END_INDEX_TOOL") and "LIST 19" in kept and "LIST 0\n" not in kept


# --- a turn's context -----------------------------------------------------------------------------


def _session(workspace: Path, storage: _Storage, *, branch="main") -> MemorySession:
    return MemorySession(
        policy=FilePolicy(workspace), registration=ProjectRegistration("p", 1, "git:p", str(workspace), created=False), storage_for=lambda scope: storage,
        embedder_for=lambda: None, embedding_identity="e@1", parser_version="v1", manifest_root=workspace.parent / "manifests", branch_of=lambda root: branch,
    )


def _assemble(turn, task="how does helper work", **kwargs):
    return turn.assemble(run_id="run-1", task=task, selection_text=kwargs.pop("selection_text", task), model_id="m", estimate=len, usable_input_tokens=kwargs.pop("usable", 40_000))


def test_a_turn_shows_verified_excerpts_scope_and_writes_a_manifest_without_bodies(workspace):
    storage = _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE), lines=(6, 7), signature="def helper():")])
    session = _session(workspace, storage)
    result = _assemble(session.turn())
    assert "return 'needle here'" in result.text
    assert "scope: index generation 3, complete" in result.text and "covers only this scope" in result.text
    assert result.file_sha256s == {"pkg/a.py": _sha(SOURCE)}
    written = next((workspace.parent / "manifests").rglob("run-1.json")).read_text(encoding="utf-8")
    manifest = json.loads(written)
    assert manifest["selected"][0]["disclosure"] == "body" and manifest["retrieval"]["generation"] == 3
    assert "needle" not in written


def test_a_file_the_task_names_is_required_and_whole(workspace):
    result = _assemble(_session(workspace, _Storage()).turn(), task="explain pkg/a.py please")
    assert SOURCE in result.text and result.prioritized_paths == ("pkg/a.py",)


def test_naming_a_secret_file_is_refused_as_today(workspace):
    result = _assemble(_session(workspace, _Storage()).turn(), task="show me .env")
    assert result.blocking_stop_reason == "WORKSPACE_REFERENCE_NOT_READABLE" and result.text == ""


def test_a_required_file_over_the_budget_is_too_large_so_agent_can_read_ranges(workspace):
    result = _assemble(_session(workspace, _Storage()).turn(), task="explain pkg/a.py", usable=100)
    assert result.blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"
    assert result.diagnostics[0].candidates == ("pkg/a.py",)


def test_without_a_generation_it_is_todays_context_with_a_line_saying_so(workspace):
    result = _assemble(_session(workspace, _Storage(current=False)).turn())
    assert "--- pkg/a.py ---" in result.text and "no usable generation (unpublished)" in result.text


def test_a_stale_pick_asks_for_reconciliation_then_reports_incomplete(workspace, monkeypatch):
    monkeypatch.setattr("optimus.context.memory_session.time.sleep", lambda seconds: None)
    storage = _Storage([_record("x", "pkg/a.py", "helper", _sha("older"), signature="def old():")])
    session = _session(workspace, storage)
    result = _assemble(session.turn())
    assert "def old" not in result.text and "incomplete: 1 files changed since they were indexed" in result.text
    assert session._priorities() == ("pkg/a.py",)
    assert sum(1 for op, _ in storage.calls if op == "coverage") == 3  # the first look and at most two retries


def test_changing_branch_moves_to_that_branchs_line(workspace):
    scopes = []
    branch = ["main"]
    storage = _Storage()

    def storage_for(scope):
        scopes.append(scope)
        return storage

    session = MemorySession(policy=FilePolicy(workspace), registration=ProjectRegistration("p", 1, "git:p", str(workspace), created=False), storage_for=storage_for, embedder_for=lambda: None,
                            embedding_identity="e@1", parser_version="v1", manifest_root=workspace.parent / "m", branch_of=lambda root: branch[0])
    session.turn()
    branch[0] = "other"
    session.turn()
    assert len(set(scopes)) == 2


def test_status_is_one_content_free_line(workspace):
    assert _session(workspace, _Storage(complete=False)).status() == "Context index: building, 2 of 9 files."
    assert _session(workspace, _Storage()).status() == "Context index: ready, 2 of 2 files."
    assert "nothing published" in _session(workspace, _Storage(current=False)).status()


def test_named_symbols_are_code_shaped_words_only():
    assert named_symbols("look at parseFile and a.b.c and snake_case, not Plain words") == ("parseFile", "a.b.c", "snake_case")
    assert named_symbols("see `run`") == ("run",)


def test_grounding_reports_what_is_not_there_and_never_claims_absence_during_a_build(workspace):
    turn = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE))], complete=True)).turn()
    report = turn.ground("See a.py and pkg/gone.py, `helper` and `missing_name`.")
    assert report.resolved == ("pkg/a.py", "helper") and set(report.unresolved) == {"pkg/gone.py", "missing_name"}
    assert "pkg/gone.py" in (report.note() or "")
    building = _session(workspace, _Storage(complete=False)).turn().ground("`missing_name`")
    assert building.unresolved == ()


def test_grounding_says_when_a_name_is_ambiguous(workspace):
    (workspace / "other").mkdir()
    (workspace / "other" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert _session(workspace, _Storage()).turn().ground("see a.py").ambiguous == ("a.py",)
    assert GroundingReport().note() is None


# --- layouts --------------------------------------------------------------------------------------


def test_the_indexed_chat_layout_keeps_what_changes_last():
    text = build_indexed_chat_input("the question", workspace_context="PACK", conversation_envelope="HISTORY", repo_map="MAP", index_results="RESULTS", tools_enabled=True)
    assert text.index("SEARCH <words>") < text.index("MAP") < text.index("HISTORY") < text.index("PACK") < text.index("RESULTS") < text.index("the question")


def test_two_questions_share_the_prefix_up_to_the_history():
    first = build_indexed_chat_input("one", workspace_context="A", conversation_envelope="HISTORY", repo_map="MAP", index_results="", tools_enabled=True)
    second = build_indexed_chat_input("two", workspace_context="B", conversation_envelope="HISTORY", repo_map="MAP", index_results="", tools_enabled=True)
    assert first[: first.index("A\n")] == second[: second.index("B\n")]


def test_withdrawn_tools_leave_the_grammar_and_state_the_limit():
    text = build_indexed_chat_input("q", workspace_context="", conversation_envelope="", repo_map="", index_results="", tools_enabled=False, limit_observation="LIMIT")
    assert "SEARCH <words>" not in text and "LIMIT" in text


def test_the_indexed_planner_layout_moves_task_and_turn_lines_last():
    base = {"planning_turn": 2, "max_planning_turns": 7, "remaining_wall_clock_minutes": 30, "conversation_envelope": "HISTORY", "initial_workspace_context": "PACK"}
    text = build_multi_turn_planner_input("THE TASK", repo_map="MAP", index_results="RESULTS", index_tools_enabled=True, **base)
    assert text.index("Respond using exactly one") < text.index("SEARCH <words>") < text.index("MAP") < text.index("HISTORY") < text.index("PACK") < text.index("RESULTS") < text.index("THE TASK") < text.index("Planning turn: 2")


def test_without_an_index_both_prompts_have_no_trace_of_it():
    chat = build_agent_planner_input("q", workspace_context="f", conversation_envelope="h", advisory=True)
    planner = build_multi_turn_planner_input("t", planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30)
    for text in (chat, planner):
        assert "SEARCH <words>" not in text and "INDEXED_" not in text and "Repository map" not in text


# --- Chat's rounds, through the real runner --------------------------------------------------------


class _Gateway:
    def __init__(self, replies):
        self.replies = list(replies)
        self.inputs: list[str] = []

    def create_response(self, *, model, input_text, metadata=None):
        self.inputs.append(input_text)
        number = len(self.inputs)
        return GatewayResponse(
            response_id=f"r{number}",
            output_text=self.replies.pop(0),
            gateway_usage=GatewayUsage(gateway_request_id=f"g{number}", provider="openrouter", billing_units=2, cost_usd=Decimal("0.01")),
            raw={"id": f"r{number}"},
        )


class _Packer:
    model_id = "m"
    usable_input_tokens = 40_000
    route_stopped = False
    estimate_request = staticmethod(len)

    def __init__(self, memory):
        self.memory = memory
        self.dispatched: list[str] = []

    def fit(self, build):
        return build("")

    def record_dispatch(self, text):
        self.dispatched.append(text)


def _chat(workspace: Path, replies, *, storage: _Storage | None = None):
    gateway = _Gateway(replies)
    runner = AgentRunner(gateway_client=gateway, model="m")
    packer = _Packer(_session(workspace, storage or _Storage()).turn())
    result = runner.run(AgentRunRequest(run_id="run-1", session_id="s", task="how does it work", execution_mode=ExecutionMode.CHAT, workspace_root=workspace), context_packer=packer)
    return result, gateway, packer


def test_chat_answers_at_once_when_it_needs_no_search(workspace):
    result, gateway, _ = _chat(workspace, ["It works like this."])
    assert result.status is AgentRunStatus.COMPLETED and result.output_text == "It works like this."
    assert len(gateway.inputs) == 1 and result.tool_calls == ()


def test_chat_runs_tools_then_answers_with_their_results_and_counts_every_call(workspace):
    result, gateway, packer = _chat(workspace, ["LIST .\nOUTLINE pkg/a.py", "Done."])
    assert result.output_text == "Done." and [call.tool_name for call in result.tool_calls] == ["index_list", "index_outline"]
    assert "Parser.parse" in gateway.inputs[1] and "INDEX_TOOL LIST ." in gateway.inputs[1]
    assert result.total_cost_usd == Decimal("0.02") and len(packer.dispatched) == 2


def test_chat_stops_at_four_rounds_then_one_call_with_tools_withdrawn(workspace):
    replies = [f"SEARCH round {i}" for i in range(MAX_INDEX_ROUNDS)] + ["Here is what I found."]
    result, gateway, _ = _chat(workspace, replies)
    assert len(gateway.inputs) == MAX_INDEX_ROUNDS + 1 == 5
    assert all("SEARCH <words>" in text for text in gateway.inputs[:4]) and "SEARCH <words>" not in gateway.inputs[4]
    assert "used every search round" in gateway.inputs[4]
    assert result.status is AgentRunStatus.COMPLETED and "stopped searching" in result.output_text and result.total_cost_usd == Decimal("0.05")


def test_there_is_no_fifth_round_even_if_the_model_keeps_asking(workspace):
    replies = [f"SEARCH round {i}" for i in range(MAX_INDEX_ROUNDS)] + ["SEARCH one more"]
    result, gateway, _ = _chat(workspace, replies)
    assert result.stop_reason == "CHAT_SEARCH_LIMIT_REACHED" and "SEARCH one more" not in result.output_text
    assert len(gateway.inputs) == 5 and len(result.tool_calls) == 4 and result.total_cost_usd == Decimal("0.05")


def test_repeating_itself_ends_the_search_rounds_early(workspace):
    result, gateway, _ = _chat(workspace, ["SEARCH same", "SEARCH same", "Answer."])
    assert len(gateway.inputs) == 3 and len(result.tool_calls) == 1 and "SEARCH <words>" not in gateway.inputs[2]


@pytest.mark.parametrize("hostile", ["WRITE pkg/a.py\nowned", "TEST pytest", 'MCP_CALL s t {"a":1}', "READ .env"])
def test_chat_with_tools_still_executes_no_directive(workspace, hostile):
    before = (workspace / "pkg" / "a.py").read_bytes()
    result, gateway, _ = _chat(workspace, [hostile])
    assert result.output_text == hostile.strip() and len(gateway.inputs) == 1 and result.tool_calls == ()
    assert (workspace / "pkg" / "a.py").read_bytes() == before


def test_a_failed_later_round_keeps_the_earlier_cost_and_calls(workspace):
    result, gateway, _ = _chat(workspace, ["LIST .", "   "])
    assert result.stop_reason == "CHAT_EMPTY_ANSWER" and result.total_cost_usd == Decimal("0.02") and len(result.tool_calls) == 1


def test_a_chat_without_an_index_keeps_its_one_call_contract(workspace):
    gateway = _Gateway(["LIST ."])
    result = AgentRunner(gateway_client=gateway, model="m").run(AgentRunRequest(run_id="run-1", session_id="s", task="q", execution_mode=ExecutionMode.CHAT, workspace_root=workspace))
    assert result.output_text == "LIST ." and len(gateway.inputs) == 1 and result.tool_calls == ()


def test_results_keep_hit_shape_for_the_wire():
    assert Hit.from_wire(_record("x", "a.py", "s", "0" * 64)).symbol == "s"


# --- Agent's planning turns, through the real runner -----------------------------------------------


def _agent(workspace: Path, replies, *, storage: _Storage | None = None):
    gateway = _Gateway(replies)
    packer = _Packer(_session(workspace, storage or _Storage()).turn())
    request = AgentRunRequest(run_id="run-1", session_id="s", task="change it", execution_mode=ExecutionMode.AGENT, workspace_root=workspace)
    return AgentRunner(gateway_client=gateway, model="m").run(request, context_packer=packer), gateway


def test_agent_can_search_then_settle_and_the_results_reach_its_next_turn(workspace):
    result, gateway = _agent(workspace, ["OUTLINE pkg/a.py", "REFUSE: not enough evidence"])
    assert [call.tool_name for call in result.tool_calls] == ["index_outline"]
    assert "Parser.parse" in gateway.inputs[1] and result.stop_reason is not None


def test_agent_search_rounds_are_on_top_of_its_planning_turns(workspace):
    replies = [f"SEARCH round {i}" for i in range(MAX_INDEX_ROUNDS)] + ["REFUSE: done"]
    result, gateway = _agent(workspace, replies)
    assert len(result.tool_calls) == MAX_INDEX_ROUNDS and len(gateway.inputs) == MAX_INDEX_ROUNDS + 1
    assert "SEARCH <words>" not in gateway.inputs[-1]


def test_after_its_rounds_agent_tool_lines_are_no_longer_grammar(workspace):
    replies = [f"SEARCH round {i}" for i in range(MAX_INDEX_ROUNDS)] + ["SEARCH one more", "REFUSE: done"]
    result, gateway = _agent(workspace, replies)
    assert len(result.tool_calls) == MAX_INDEX_ROUNDS
    assert "not accepted" in gateway.inputs[MAX_INDEX_ROUNDS + 1]


def test_a_tool_line_inside_a_plan_is_not_a_request_and_a_plan_still_needs_approval(workspace):
    before = (workspace / "pkg" / "a.py").read_bytes()
    result, _ = _agent(workspace, ["READ pkg/a.py\nWRITE pkg/a.py\nowned\nSEARCH not a tool\n"])
    assert not [call for call in result.tool_calls if call.tool_name.startswith("index_")]
    assert result.status is AgentRunStatus.AWAITING_APPROVAL and (workspace / "pkg" / "a.py").read_bytes() == before


def test_an_agent_without_an_index_has_no_such_grammar(workspace):
    gateway = _Gateway(["REFUSE: done"])
    AgentRunner(gateway_client=gateway, model="m").run(AgentRunRequest(run_id="run-1", session_id="s", task="t", execution_mode=ExecutionMode.AGENT, workspace_root=workspace))
    assert "SEARCH <words>" not in gateway.inputs[0] and "INDEXED_" not in gateway.inputs[0]
