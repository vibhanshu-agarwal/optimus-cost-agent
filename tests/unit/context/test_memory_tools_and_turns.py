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
from context_engine.index_worker import StorageUnavailableError
from context_engine.retrieval import Hit, Retriever
from optimus.agent.directives import IndexToolRequest, parse_index_tool_reply
from optimus.agent.index_turn import MAX_INDEX_ROUNDS, keep_newest, run_index_tools
from optimus.agent.models import AgentRunRequest, AgentRunStatus
from optimus.agent.prompts import build_agent_planner_input, build_indexed_chat_input, build_multi_turn_planner_input
from optimus.agent.runner import AgentRunner
from optimus.agent.tools import AgentToolbox
from optimus.context.index_tools import IndexTools
from optimus.context.memory_session import GroundingReport, MemorySession, _Scope, named_symbols
from optimus.context.project_registry import ProjectRegistration
from optimus.gateway.models import GatewayResponse, GatewayUsage
from optimus.guardrails import file_policy
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


# --- what the index cannot answer -----------------------------------------------------------------


class _BrokenEmbedder:
    def embed(self, texts):
        raise RuntimeError("native failure")


def test_a_model_that_fails_is_a_search_that_did_not_answer_and_never_a_failed_turn():
    result = Retriever(_Storage(), _BrokenEmbedder()).retrieve("helper")
    assert result.state == "ok" and result.channels["dense"] == "unavailable" and result.channels["lexical"] == "0 results"


def test_search_never_reads_a_search_that_did_not_answer_as_no_matches(workspace):
    storage = _Storage()
    answer = IndexTools(retriever=Retriever(storage, _BrokenEmbedder()), storage=storage, read=lambda path: None, listing=lambda: []).run("SEARCH", "helper")
    assert "No matches in this scope." in answer and "did not answer" in answer and "dense unavailable" in answer


def test_a_term_or_name_the_route_would_refuse_is_left_out_before_it_gets_there(workspace):
    storage = _Storage()
    Retriever(storage, None).retrieve("real_term " + "a" * 65, named_symbols=("b" * 257, "kept_name"))
    lexical = next(fields for op, fields in storage.calls if fields.get("mode") == "lexical")
    assert "real_term" in lexical["terms"] and all(len(term) <= 64 for term in lexical["terms"])
    assert [fields["symbol"] for op, fields in storage.calls if fields.get("mode") == "symbol"] == ["kept_name"]
    storage.calls.clear()
    assert "No matching symbols" in _tools(workspace, storage).run("SYMBOLS", "c" * 257)
    assert not any(fields.get("mode") == "symbol" for _op, fields in storage.calls)


def test_a_worker_that_fails_says_so_rather_than_building_forever(workspace):
    class Broken:
        identity, dimensions = "e@1", 8

        def embed(self, texts):
            raise RuntimeError("native failure")

    session = MemorySession(policy=FilePolicy(workspace), registration=ProjectRegistration("p", 1, "git:p", str(workspace), created=False), storage_for=lambda scope: _Opening(), embedder_for=Broken,
                            embedding_identity="e@1", parser_version="v1", manifest_root=workspace.parent / "m", branch_of=lambda root: "main")
    session.start()
    assert session._thread is not None
    session._thread.join(10)
    assert not session._thread.is_alive()
    assert session.status().startswith("Context index: not updating (INDEX_WORKER_FAILED:RuntimeError)")


class _Opening(_Storage):
    """Just enough of a storage port for a worker to reach its first embedding."""

    def call(self, op, **fields):
        if op == "generation":
            return {"status": "ok", "epoch": 1, "resume_epoch": None, "building": None, "current": None, "cursor": None}
        if op == "lease":
            return {"status": "ok", "token": 1}
        if op == "catalogue":
            return {"status": "ok", "files": [], "cursor": None, "unfinished": []}
        return super().call(op, **fields)


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
    assert "read 2 of 2 admitted files now." in text


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
    assert "read now" in text and "Parser.parse" in text and "helper" in text


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
    memory.on_tool = lambda call_id, phase, tool, argument, summary: cards.append((phase, tool, argument))
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
    session = MemorySession(
        policy=FilePolicy(workspace), registration=ProjectRegistration("p", 1, "git:p", str(workspace), created=False), storage_for=lambda scope: storage,
        embedder_for=lambda: None, embedding_identity="e@1", parser_version="v1", manifest_root=workspace.parent / f"{workspace.name}-manifests", branch_of=lambda root: branch,
    )
    session.disk_facts = lambda: ("r" * 64, 0)  # type: ignore[method-assign]  # the disk matches what the table says was published; real revisions are in tests/integration/context
    session.dirty_paths = lambda: ()  # type: ignore[method-assign]
    return session


def _assemble(turn, task="how does helper work", **kwargs):
    return turn.assemble(run_id="run-1", task=task, selection_text=kwargs.pop("selection_text", task), model_id="m", estimate=len, usable_input_tokens=kwargs.pop("usable", 40_000))


def test_a_turn_shows_verified_excerpts_scope_and_writes_a_manifest_without_bodies(workspace):
    storage = _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE), lines=(6, 7), signature="def helper():")])
    session = _session(workspace, storage)
    result = _assemble(session.turn())
    assert "return 'needle here'" in result.text
    assert "scope: index generation 3, complete" in result.text and "covers only this scope" in result.text
    assert result.file_sha256s == {"pkg/a.py": _sha(SOURCE)}
    written = next((workspace.parent / f"{workspace.name}-manifests").rglob("run-1.json")).read_text(encoding="utf-8")
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


# --- the editor's unsaved text ---------------------------------------------------------------------


UNSAVED = "class Parser:\n    def parse(self, text):\n        return text\n\n\ndef unsaved_helper():\n    return 'unsaved needle'\n"


def _buffered(workspace: Path, buffers: dict, *, storage: _Storage | None = None):
    """A turn whose editor holds `buffers`, keyed by path, and which records what it was asked."""
    asked: list[str] = []

    def read_buffer(path: str) -> str | None:
        asked.append(Path(path).relative_to(workspace).as_posix())
        return buffers.get(asked[-1], SOURCE)

    turn = _session(workspace, storage or _Storage()).turn()
    turn.read_buffer = read_buffer
    return turn, asked


def test_a_dirty_buffer_is_what_the_turn_sees_and_it_says_so(workspace):
    turn, asked = _buffered(workspace, {"pkg/a.py": UNSAVED})
    result = _assemble(turn, task="explain pkg/a.py")
    assert asked == ["pkg/a.py"]
    assert "unsaved needle" in result.text and "'needle here'" not in result.text
    assert "shown from the editor's unsaved text, which differs from disk: pkg/a.py" in result.text
    assert result.file_sha256s == {"pkg/a.py": _sha(UNSAVED)}  # an EDIT bound to this digest is refused until the file on disk agrees
    assert (workspace / "pkg" / "a.py").read_text(encoding="utf-8") == SOURCE


def test_a_saved_buffer_is_the_control_and_no_overlay_exists(workspace):
    turn, asked = _buffered(workspace, {"pkg/a.py": SOURCE})
    result = _assemble(turn, task="explain pkg/a.py")
    assert asked == ["pkg/a.py"] and "unsaved" not in result.text and result.file_sha256s == {"pkg/a.py": _sha(SOURCE)}


def test_a_saved_crlf_file_is_not_an_unsaved_edit_because_the_editor_shows_lf(workspace):
    (workspace / "pkg" / "a.py").write_bytes(SOURCE.replace("\n", "\r\n").encode("utf-8"))
    turn, _asked = _buffered(workspace, {"pkg/a.py": SOURCE})
    assert "unsaved" not in _assemble(turn, task="explain pkg/a.py").text


def test_a_denied_file_is_never_asked_for(workspace):
    turn, asked = _buffered(workspace, {".env": "TOKEN=unsaved"})
    result = _assemble(turn, task="show me .env")
    assert asked == [] and result.blocking_stop_reason == "WORKSPACE_REFERENCE_NOT_READABLE" and "unsaved" not in result.text


def test_only_named_files_are_asked_for_so_unsaved_work_is_not_searched(workspace):
    storage = _Storage([_record("x", "notes.md", None, _sha("# Title\n\nSome prose.\n"), kind="file")])
    turn, asked = _buffered(workspace, {"notes.md": "unsaved note"}, storage=storage)
    result = _assemble(turn, task="how does helper work")
    assert asked == [] and "unsaved note" not in result.text


def test_an_editor_that_gives_nothing_means_disk_and_is_not_asked_again(workspace):
    (workspace / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    calls: list[str] = []

    def no_answer(path: str) -> None:
        calls.append(path)

    turn = _session(workspace, _Storage()).turn()
    turn.read_buffer = no_answer
    result = _assemble(turn, task="explain pkg/a.py and pkg/b.py")
    assert len(calls) == 1 and "'needle here'" in result.text and "unsaved" not in result.text


def test_tools_and_grounding_agree_with_the_buffer_the_turn_saw(workspace):
    storage = _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE), lines=(6, 7), signature="def helper():")])
    turn, _asked = _buffered(workspace, {"pkg/a.py": UNSAVED}, storage=storage)
    _assemble(turn, task="explain pkg/a.py")
    assert "unsaved_helper" in turn.tools.run("OUTLINE", "pkg/a.py")
    assert "unsaved needle" in turn.tools.run("SEARCH", '"unsaved needle"')
    searched = turn.tools.run("SYMBOLS", "helper")
    assert "unsaved_helper" in searched and "(unsaved)" in searched and "their files changed" in searched  # the index's record is of the text on disk
    report = turn.ground("`unsaved_helper` is new and `invented_name` is not, and `helper` was replaced.")
    assert report.resolved == ("unsaved_helper",) and report.not_in_index == ("invented_name",)  # the generation does hold `helper`, so nothing is said of it


def test_an_unsaved_buffer_never_reaches_the_manifest(workspace):
    turn, _asked = _buffered(workspace, {"pkg/a.py": UNSAVED})
    _assemble(turn, task="explain pkg/a.py")
    written = next((workspace.parent / f"{workspace.name}-manifests").rglob("run-1.json")).read_text(encoding="utf-8")
    assert json.loads(written)["unsaved_buffers"] == ["pkg/a.py"] and "unsaved needle" not in written and "unsaved_helper" not in written


def test_each_turn_asks_again_so_a_saved_or_changed_buffer_leaves_no_trace(workspace):
    buffers = {"pkg/a.py": UNSAVED}
    session = _session(workspace, _Storage())

    def assemble():
        turn = session.turn()
        turn.read_buffer = lambda path: buffers["pkg/a.py"]
        return _assemble(turn, task="explain pkg/a.py")

    assert "unsaved needle" in assemble().text
    buffers["pkg/a.py"] = SOURCE
    second = assemble()
    assert "unsaved needle" not in second.text and "unsaved text" not in second.text


def test_when_the_index_cannot_answer_nothing_this_turn_sees_the_buffer(workspace):
    turn, _asked = _buffered(workspace, {"pkg/a.py": UNSAVED}, storage=_Storage(current=False))
    result = _assemble(turn, task="explain pkg/a.py")
    assert "no usable generation" in result.text and "unsaved needle" not in result.text
    assert "unsaved_helper" not in turn.tools.run("OUTLINE", "pkg/a.py")


@pytest.mark.parametrize("kind", ["binary", "too large"])
def test_a_buffer_this_turn_could_not_use_means_disk(workspace, kind):
    turn, _asked = _buffered(workspace, {"pkg/a.py": "a\x00b" if kind == "binary" else "x" * (8 * 1024 * 1024 + 1)})
    assert "'needle here'" in _assemble(turn, task="explain pkg/a.py", usable=10**9).text


def test_named_symbols_are_code_shaped_words_only():
    assert named_symbols("look at parseFile and a.b.c and snake_case, not Plain words") == ("parseFile", "a.b.c", "snake_case")
    assert named_symbols("see `run`") == ("run",)


def test_grounding_reports_what_is_not_there_and_never_claims_absence_during_a_build(workspace):
    turn = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE))], complete=True)).turn()
    report = turn.ground("See a.py and pkg/gone.py, `helper` and `missing_name`.")
    assert report.resolved == ("pkg/a.py", "helper") and report.unresolved == ("pkg/gone.py",) and report.not_in_index == ("missing_name",)
    assert "pkg/gone.py" in (report.note() or "")
    assert "no definition in index generation 3, and the disk was not exhaustively checked: missing_name" in (report.note() or "")
    building = _session(workspace, _Storage(complete=False)).turn().ground("`missing_name`")
    assert building.not_in_index == ()


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


# --- what review 1 found ----------------------------------------------------------------------------


def _ignore(workspace: Path, text: str) -> None:
    (workspace / ".optimusignore").write_text(text, encoding="utf-8")


def _mapped(workspace: Path) -> tuple[MemorySession, _Scope]:
    records = [_record("x", "pkg/a.py", "helper", _sha(SOURCE), lines=(6, 7)), _record("n", "notes.md", None, _sha("# Title\n\nSome prose.\n"), kind="file")]
    session = _session(workspace, _Storage(records))
    return session, session._current_scope()


def test_the_map_is_stable_while_nothing_changes(workspace):
    session, scope = _mapped(workspace)
    first = session.repo_map(scope)
    assert "pkg/a.py: helper" in first and "notes.md" in first
    assert session.repo_map(scope) == first


def test_the_map_drops_a_file_the_policy_now_refuses_at_once(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    _ignore(workspace, "pkg/\n")
    assert "pkg/a.py" not in session.repo_map(scope)


def test_the_map_drops_a_deleted_file_at_once(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    (workspace / "notes.md").unlink()
    assert "notes.md" not in session.repo_map(scope)


def test_a_changed_file_keeps_its_path_and_loses_its_symbols_at_once(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    (workspace / "pkg" / "a.py").write_text("def other():\n    return 1\n", encoding="utf-8")
    text = session.repo_map(scope)
    assert "pkg/a.py" in text and "helper" not in text


def test_a_map_kept_through_an_outage_is_still_checked(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    session._map.at = -10_000.0

    def down(op, **fields):
        raise StorageUnavailableError("gone")

    scope.storage.call = down
    (workspace / "notes.md").unlink()
    text = session.repo_map(scope)
    assert "pkg/a.py" in text and "notes.md" not in text


def test_a_policy_change_takes_back_unsaved_text_the_turn_already_holds(workspace):
    session = _session(workspace, _Storage())
    turn = session.turn()
    turn.read_buffer = lambda path: UNSAVED
    assert "unsaved needle" in _assemble(turn, task="explain pkg/a.py").text
    _ignore(workspace, "pkg/\n")
    assert "cannot be read" in turn.tools.run("OUTLINE", "pkg/a.py")
    assert "unsaved needle" not in turn.tools.run("SEARCH", '"unsaved needle"')
    assert "unsaved_helper" not in turn.tools.run("SYMBOLS", "unsaved_helper")
    assert "unsaved_helper" not in turn.ground("`unsaved_helper`").resolved


def test_grounding_says_a_symbol_with_two_verified_owners_is_ambiguous(workspace):
    (workspace / "pkg" / "b.py").write_text(SOURCE, encoding="utf-8", newline="\n")
    records = [_record("x", "pkg/a.py", "helper", _sha(SOURCE)), _record("y", "pkg/b.py", "helper", _sha(SOURCE))]
    assert _session(workspace, _Storage(records)).turn().ground("`helper`").ambiguous == ("helper",)


def test_a_record_of_changed_text_proves_nothing_either_way(workspace):
    records = [_record("x", "pkg/a.py", "helper", _sha("older text"))]
    session = _session(workspace, _Storage(records))
    report = session.turn().ground("`helper`")
    assert report.resolved == () and report.not_in_index == ()
    assert session._priorities() == ("pkg/a.py",), "a proved change gets its pass"


def test_absence_is_not_claimed_from_a_generation_older_than_the_disk(workspace):
    session = _session(workspace, _Storage())
    session.disk_facts = lambda: ("s" * 64, 0)  # a file has changed since this complete generation
    assert session.turn().ground("`added_since`").not_in_index == ()


def test_absence_is_not_claimed_where_the_parser_cannot_see(workspace):
    class Unsupported(_Storage):
        def call(self, op, **fields):
            reply = super().call(op, **fields)
            if op == "coverage":
                reply["current"]["coverage"]["unsupported"] = 3
            return reply

    assert _session(workspace, Unsupported()).turn().ground("`written_in_kotlin`").not_in_index == ()


def test_grounding_asks_for_the_disk_only_once_and_only_if_something_looks_absent(workspace):
    session = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE))]))
    asked = []
    session.disk_facts = lambda: asked.append(1) or ("r" * 64, 0)
    session.turn().ground("`helper`")
    assert asked == []
    session.turn().ground("`one_name` and `other_name`")
    assert asked == [1]


def test_a_turn_keeps_its_own_scopes_catalogue_after_a_switch(workspace):
    stores = {}
    branch = ["main"]

    def storage_for(scope):
        return stores.setdefault(scope, _Storage([_record(scope[:6], "pkg/a.py", "helper", _sha(SOURCE))]))

    session = MemorySession(policy=FilePolicy(workspace), registration=ProjectRegistration("p", 1, "git:p", str(workspace), created=False), storage_for=storage_for, embedder_for=lambda: None,
                            embedding_identity="e@1", parser_version="v1", manifest_root=workspace.parent / "m2", branch_of=lambda root: branch[0])
    old = session.turn()
    first = next(iter(stores.values()))
    branch[0] = "other"
    session.turn()
    second = next(store for store in stores.values() if store is not first)
    second.calls.clear()
    old._retriever.retrieve("helper")
    assert second.calls == [], "an old turn read another branch's line with its own epoch number"
    assert any(op == "catalogue" for op, _fields in first.calls)


def test_a_complete_generation_never_reuses_an_older_catalogue(workspace):
    class Moving(_Storage):
        epoch = 3

        def call(self, op, **fields):
            reply = super().call(op, **fields)
            if op == "coverage":
                reply["current"]["epoch"] = self.epoch
            return reply

    storage = Moving([_record("x", "pkg/a.py", "helper", _sha(SOURCE))])
    session = _session(workspace, storage)
    session.turn()._retriever.retrieve("helper")
    storage.epoch = 4
    session.turn()._retriever.retrieve("helper")
    assert [fields["epoch"] for op, fields in storage.calls if op == "catalogue"] == [3, 4]


def test_a_build_may_reuse_a_recent_catalogue_since_it_only_suggests_what_to_ask(workspace):
    class Moving(_Storage):
        epoch = 3

        def call(self, op, **fields):
            reply = super().call(op, **fields)
            if op == "coverage":
                reply["current"]["epoch"] = self.epoch
            return reply

    storage = Moving([_record("x", "pkg/a.py", "helper", _sha(SOURCE))], complete=False)
    session = _session(workspace, storage)
    session.turn()._retriever.retrieve("helper")
    storage.epoch = 4
    assert [fields["epoch"] for op, fields in storage.calls if op == "catalogue"] == [3]
    storage.calls.clear()
    second = session.turn()._retriever.retrieve("helper")
    assert second.epoch == 4 and not any(op == "catalogue" for op, _fields in storage.calls)
    assert {fields["epoch"] for op, fields in storage.calls if op == "query"} == {4}  # every record comes from the retrieval's own epoch


def test_a_file_too_large_to_index_is_still_listed_searched_and_named(workspace):
    big = "line of text\n" * 90_000
    (workspace / "big.txt").write_text(big, encoding="utf-8")
    session = _session(workspace, _Storage())
    tools = session.turn().tools
    assert "big.txt" in tools.run("LIST", ".")
    assert "big.txt:1:" in tools.run("SEARCH", '"line of text"')
    assert _assemble(session.turn(), task="explain big.txt").blocking_stop_reason == "REQUIRED_WORKSPACE_FILE_TOO_LARGE"


def test_a_quoted_search_counts_only_what_it_read_and_names_what_it_could_not_see(workspace):
    (workspace / "image.bin").write_bytes(b"a\x00b")
    tools = _session(workspace, _Storage()).turn().tools
    answer = tools.run("SEARCH", '"nothing like this"')
    assert "read 2 of 3 admitted files now." in answer and "1 are binary, empty or could not be read" in answer and "No matches" in answer


def test_a_folder_that_cannot_be_listed_is_named_by_the_disk_tools(workspace, monkeypatch):
    real = file_policy.os.scandir

    def scandir(path):
        if str(path).endswith("pkg"):
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(file_policy.os, "scandir", scandir)
    tools = _session(workspace, _Storage()).turn().tools
    assert "1 folders could not be listed" in tools.run("SEARCH", '"needle here"')
    assert "1 folders could not be listed" in tools.run("LIST", ".")


def test_the_turn_lets_the_worker_run_during_its_wait_for_a_repair(workspace, monkeypatch):
    session = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha("older"), signature="def old():")]))
    busy_during_wait = []
    monkeypatch.setattr("optimus.context.memory_session.time.sleep", lambda seconds: busy_during_wait.append(session._busy.is_set()))
    busy_during_retrieval = []
    real = session._read

    def read(path):
        busy_during_retrieval.append(session._busy.is_set())
        return real(path)

    session._read = read
    _assemble(session.turn())
    assert busy_during_wait == [False, False] and True in busy_during_retrieval and not session._busy.is_set()


def test_a_cancel_stops_asking_the_editor(workspace):
    (workspace / "pkg" / "b.py").write_text("def b():\n    return 2\n", encoding="utf-8")
    cancelled = [False]
    asked = []

    def read_buffer(path):
        asked.append(path)
        cancelled[0] = True
        return UNSAVED

    turn = _session(workspace, _Storage()).turn(cancelled=lambda: cancelled[0])
    turn.read_buffer = read_buffer
    _assemble(turn, task="explain pkg/a.py and pkg/b.py")
    assert len(asked) == 1


def test_a_tool_call_is_recorded_once_with_its_facts_and_never_its_search_text(workspace):
    events = []
    cards = []
    memory = _memory(_tools(workspace, _Storage()))
    memory.on_tool = lambda call_id, phase, tool, argument, summary: cards.append(call_id)
    requests = (IndexToolRequest("SEARCH", "secret words here"), IndexToolRequest("LIST", "."), IndexToolRequest("OUTLINE", "../x"))
    run_index_tools(requests, memory, _toolbox(workspace), event_sink=events.append, run_id="run-9", session_id="s-9")
    search, listing, refused = (event.payload for event in events)
    assert [event.run_id for event in events] == ["run-9"] * 3 and {event.session_id for event in events} == {"s-9"}
    assert [event.request_id for event in events] == cards[::2] and cards[0] == cards[1] and cards[0] != cards[2]
    assert search["tool_name"] == "index_search" and search["parameters"]["argument_chars"] == 17 and "secret" not in str(search)
    assert search["parameters"]["argument_sha256"] == hashlib.sha256(b"secret words here").hexdigest()  # pragma: allowlist secret - the digest of a test string
    assert search["authorization_outcome"] == "ALLOW" and isinstance(search["latency_ms"], int) and search["policy_reason"]
    assert listing["parameters"] == {"path": "."}
    assert refused["authorization_outcome"] == "BLOCK" and refused["policy_reason"]


def test_a_halted_turn_records_nothing_further(workspace):
    events = []
    state = [False]

    def halted():
        return state[0]

    tools = _tools(workspace, _Storage())
    memory = _memory(tools)
    memory.on_tool = lambda call_id, phase, tool, argument, summary: state.__setitem__(0, phase == "completed")
    run_index_tools((IndexToolRequest("LIST", "."),), memory, _toolbox(workspace), halted=halted, event_sink=events.append, run_id="r")
    assert events == []


# --- what review 2 found ----------------------------------------------------------------------------


def test_the_map_reads_its_hashes_from_its_own_epoch_even_during_a_build(workspace):
    class Moving(_Storage):
        epoch = 3

        def call(self, op, **fields):
            reply = super().call(op, **fields)
            if op == "coverage":
                reply["current"]["epoch"] = self.epoch
            return reply

    storage = Moving([_record("x", "pkg/a.py", "helper", _sha(SOURCE))], complete=False)
    session = _session(workspace, storage)
    session.turn()._retriever.retrieve("helper")
    storage.epoch = 4
    session.repo_map(session._current_scope())
    assert [fields["epoch"] for op, fields in storage.calls if op == "catalogue"] == [3, 4]


@pytest.mark.parametrize("damage", ["emptied", "binary"])
def test_a_file_that_can_no_longer_be_read_keeps_no_symbols_in_the_map(workspace, damage):
    session, scope = _mapped(workspace)
    assert "helper" in session.repo_map(scope)
    (workspace / "pkg" / "a.py").write_bytes(b"" if damage == "emptied" else b"a\x00b")
    text = session.repo_map(scope)
    assert "helper" not in text and "pkg/a.py" in text


def test_grounding_does_not_trust_a_listing_that_predates_a_deletion_or_an_exclusion(workspace):
    session = _session(workspace, _Storage())
    session.listing()
    (workspace / "notes.md").unlink()
    assert session.turn().ground("See notes.md.").unresolved == ("notes.md",)
    session.listing()
    _ignore(workspace, "pkg/\n")
    assert session.turn().ground("See pkg/a.py.").unresolved == ("pkg/a.py",)


def test_a_new_file_with_the_same_name_makes_a_bare_name_ambiguous_at_once(workspace):
    session = _session(workspace, _Storage())
    session.listing()
    (workspace / "other").mkdir()
    (workspace / "other" / "a.py").write_text("x = 1\n", encoding="utf-8")
    assert session.turn().ground("See a.py.").ambiguous == ("a.py",)
    assert _assemble(session.turn(), task="explain a.py").blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"


def test_absence_is_not_claimed_when_a_file_was_too_large_to_parse(workspace):
    session = _session(workspace, _Storage())
    session.disk_facts = lambda: ("r" * 64, 1)
    assert session.turn().ground("`defined_in_the_big_file`").not_in_index == ()


def test_an_empty_list_still_says_what_it_could_not_see(workspace, monkeypatch):
    real = file_policy.os.scandir

    def scandir(path):
        if str(path).endswith("pkg"):
            raise PermissionError(path)
        return real(path)

    monkeypatch.setattr(file_policy.os, "scandir", scandir)
    answer = _session(workspace, _Storage()).turn().tools.run("LIST", "pkg")
    assert "Nothing the file policy admits" in answer and "1 folders could not be listed" in answer


def test_a_long_path_argument_is_recorded_whole(workspace):
    events = []
    long_path = "a/" * 800 + "b.py"
    run_index_tools((IndexToolRequest("OUTLINE", long_path),), _memory(_tools(workspace, _Storage())), _toolbox(workspace), event_sink=events.append, run_id="r")
    assert events[0].payload["parameters"] == {"path": long_path}


# --- what review 3 found ----------------------------------------------------------------------------


def test_a_root_files_name_is_still_ambiguous_once_a_second_file_has_it(workspace):
    session = _session(workspace, _Storage())
    (workspace / "root.py").write_text("x = 1\n", encoding="utf-8")
    session.listing()
    (workspace / "other").mkdir()
    (workspace / "other" / "root.py").write_text("x = 2\n", encoding="utf-8")
    assert session.turn().ground("See root.py.").ambiguous == ("root.py",)
    assert _assemble(session.turn(), task="explain root.py").blocking_stop_reason == "AMBIGUOUS_WORKSPACE_REFERENCE"


def test_a_cached_listing_is_used_for_an_exact_path_still_admitted(workspace):
    session = _session(workspace, _Storage())
    listed = session.listing()
    assert session.listing_for(("pkg/a.py",)) is listed
    assert session.listing_for(()) is listed


def test_absence_needs_each_changed_files_bytes_to_match_the_generation(workspace):
    class FileRecords(_Storage):
        def call(self, op, **fields):
            if op == "query" and fields.get("mode") == "path":
                return {"records": [{"file_hash": self.held}]}
            return super().call(op, **fields)

    storage = FileRecords()
    session = _session(workspace, storage)
    session.dirty_paths = lambda: ("pkg/a.py",)
    storage.held = _sha("what it was before an edit that kept its size and time")
    assert session.turn().ground("`new_name`").not_in_index == ()
    assert session._priorities() == ("pkg/a.py",), "a proved change gets its pass"
    storage.held = _sha(SOURCE)
    assert session.turn().ground("`new_name`").not_in_index == ("new_name",)


def test_absence_is_not_claimed_outside_git_or_past_too_many_changes(workspace):
    session = _session(workspace, _Storage())
    session.dirty_paths = lambda: None
    assert session.turn().ground("`any_name`").not_in_index == ()
    session.dirty_paths = lambda: tuple(f"f{number}.py" for number in range(65))
    assert session.turn().ground("`any_name`").not_in_index == ()


def test_the_proof_is_asked_for_once_a_reply_and_only_if_something_looks_absent(workspace):
    session = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE))]))
    asked = []
    session.dirty_paths = lambda: asked.append(1) or ()
    session.turn().ground("`helper`")
    assert asked == []
    session.turn().ground("`one_name` and `other_name`")
    assert asked == [1]


# --- what review 4 found ----------------------------------------------------------------------------


def test_what_was_proved_for_one_generation_says_nothing_about_the_next(workspace):
    class Publishing(_Storage):
        epoch = 3

        def call(self, op, **fields):
            reply = super().call(op, **fields)
            if op == "coverage":
                reply["current"]["epoch"] = self.epoch
                self.epoch += 1  # each symbol's look finds a newer generation than the last
            return reply

    report = _session(workspace, Publishing()).turn().ground("`first_name` and `second_name`")
    assert report.not_in_index == ("first_name",) and report.generation == 3


def test_a_report_with_nothing_missing_names_no_generation(workspace):
    report = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE))])).turn().ground("`helper`")
    assert report.generation is None and report.note() is None


@pytest.mark.parametrize("tool", ["SEARCH", "SYMBOLS"])
def test_a_tool_that_finds_a_changed_file_asks_for_its_repair(workspace, tool):
    session = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha("older"), signature="def old():")]))
    session.turn().tools.run(tool, "helper")
    assert session._priorities() == ("pkg/a.py",)


@pytest.mark.parametrize("tool", ["SEARCH", "SYMBOLS"])
def test_unsaved_text_is_no_reason_to_repair_the_index(workspace, tool):
    session = _session(workspace, _Storage([_record("x", "pkg/a.py", "helper", _sha(SOURCE), signature="def helper():")]))
    turn = session.turn()
    turn.read_buffer = lambda path: UNSAVED
    _assemble(turn, task="explain pkg/a.py")
    turn.tools.run(tool, "helper")
    assert session._priorities() == ()


def test_the_map_asks_for_the_repair_and_rereads_the_generation_next_time(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    (workspace / "pkg" / "a.py").write_text("def other():\n    return 1\n", encoding="utf-8")
    session.repo_map(scope)
    assert session._priorities() == ("pkg/a.py",)
    assert session._map.at == float("-inf")


def test_a_file_that_cannot_be_read_asks_for_no_repair(workspace):
    session, scope = _mapped(workspace)
    session.repo_map(scope)
    (workspace / "pkg" / "a.py").write_bytes(b"a\x00b")
    session.repo_map(scope)
    assert session._priorities() == ()
