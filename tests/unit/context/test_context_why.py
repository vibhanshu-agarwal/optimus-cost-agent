"""Plan 12.13 `/why`: the last terminal turn's recorded context explanation, answered locally from RAM.

The module's own rules (parsing, capture, rendering, privacy and paging) are tested directly; the ACP host's are tested
through the real adapter with a runner that reports what a production run reports (its automatic context, each dispatch
and its planning progress) through the same hooks."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.agent.planning_loop import PLANNING_NEW_READ_MAX_BYTES, PLANNING_OBSERVATION_MAX_BYTES, PlanningProgressEvent
from optimus.agent.workspace_context import assemble_workspace_context_for_prompt
from optimus.context import context_why as why
from optimus.context import memory_serving
from tests.unit.acp.test_context_engine_admission import Runner, make_adapter, make_attachment, new_session, prompt, rpc, session_of, texts

LIMITS = (PLANNING_OBSERVATION_MAX_BYTES, PLANNING_NEW_READ_MAX_BYTES)
BODY_MARKER = "BODY_MARKER_TEXT = 'never shown'"


def _snapshot(**fields: Any) -> why.Snapshot:
    base: dict[str, Any] = dict(run_id="s:1", turn_seq=1, outcome="completed", stop=None, index="not configured", contexts=(), dispatches=(),
                                rounds=None, reads=None, limits=LIMITS, manifest=None, served=memory_serving.EMPTY, memory_read=None)
    return why.capture(**{**base, **fields})


def _raw(snapshot: why.Snapshot | None, page: int = 1, *, admits=lambda path: True, sanitize=lambda text: text, refused: bool = False,
         on_disk: bool = False) -> str:
    return why.answer(snapshot, page, sanitize=sanitize, admits=admits, refused_after=refused, manifests_on_disk=on_disk)


def _plain(text: str) -> str:
    """The text as Markdown shows it: escapes removed."""
    return re.sub(r"\\(.)", r"\1", text)


def _text(snapshot: why.Snapshot | None, page: int = 1, **kwargs: Any) -> str:
    return _plain(_raw(snapshot, page, **kwargs))


# --- parsing ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("text", "expected"), [("/why", 1), ("  /why  ", 1), ("/why 3", 3), ("/why 1000", 1000), ("/why 0", why.USAGE),
                                                ("/why 1001", why.USAGE), ("/why next", why.USAGE), ("/why 2 3", why.USAGE),
                                                ("/whyy", None), ("why", None), ("explain /why", None)])
def test_only_why_and_why_n_are_the_command(text, expected):
    assert why.parse(text, attachments=False) == expected


def test_an_attachment_makes_the_command_malformed():
    assert why.parse("/why", attachments=True) == why.USAGE


# --- capture and rendering ---------------------------------------------------------------------------------------------


def _ambiguous(tmp_path: Path) -> Any:
    for folder in ("src/agent", "src/gateway"):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "config.py").write_text(BODY_MARKER + "\n", encoding="utf-8")
    return assemble_workspace_context_for_prompt(tmp_path, task="fix the gateway timeout in config.py")


def test_a_blocked_turn_explains_its_ranked_stop_and_that_nothing_was_dispatched(tmp_path):
    text = _text(_snapshot(outcome="failed", stop="AMBIGUOUS_WORKSPACE_REFERENCE", contexts=[_ambiguous(tmp_path)]))

    assert "outcome: failed; stop: AMBIGUOUS_WORKSPACE_REFERENCE" in text
    assert "model requests sent: none, so this context was prepared and never dispatched" in text
    assert "config.py was ambiguous, so nothing was chosen; candidates, most likely first:\n  - src/gateway/config.py (task terms: gateway)\n  - src/agent/config.py" in text
    assert BODY_MARKER not in text and "never shown" not in text


def test_an_index_turn_shows_its_choices_ranks_fit_and_grounding_but_no_bodies():
    manifest = {"selected": [{"path": "pkg/a.py", "kind": "symbol", "symbol": "helper", "file_hash": "f" * 64, "start_line": 1, "end_line": 3,
                              "disclosure": "body", "score": 0.5, "ranks": {"lexical": 1, "dense": 2}, "reason": "matched the task"},
                             {"path": "pkg/b.py", "kind": "file", "symbol": None, "file_hash": "e" * 64, "start_line": None, "end_line": None,
                              "disclosure": "omitted", "ranks": {"dense": 7}, "reason": "over the budget"}],
                "budget": {"tokens": 120, "budget_tokens": 4096, "task_words": 3},
                "retrieval": {"state": "ok", "generation": 3, "coverage": {"files_indexed": 2, "files_total": 2}, "channels": {"dense": "ok"}},
                "grounding": {"resolved": ["pkg/a.py"], "unresolved": ["gone.py"], "ambiguous": [], "not_in_index": []},
                "unsaved_buffers": ["pkg/a.py"], "stale_paths": []}

    text = _text(_snapshot(index="used", manifest=manifest, dispatches=[(900, 40000), (1200, 40000)], rounds=2, reads=[100, 50]))

    assert "- 1. pkg/a.py helper: body; ranks: dense 2, lexical 1; matched the task" in text
    assert "- 2. pkg/b.py: omitted; ranks: dense 7; over the budget" in text
    assert "index pack: 120 of 4096 tokens" in text and "largest request: about 1200 of 40000 usable input tokens" in text
    assert f"planning limits: observations {LIMITS[0]} bytes, new reads {LIMITS[1]} bytes" in text
    assert "planning reads: 2, returning 150 bytes" in text and "model requests sent: 2; planning rounds: 2" in text
    assert "retrieval: ok; generation 3, 2 of 2 files; channels: dense ok" in text
    assert "cited but not found: gone.py" in text and "unsaved editor text: pkg/a.py" in text
    assert why.HISTORICAL in text


def test_a_snapshot_is_immutable_once_captured():
    manifest = {"selected": [{"path": "pkg/a.py", "disclosure": "body", "ranks": {}}], "budget": {"tokens": 1, "budget_tokens": 2}}
    dispatches = [(1, 2)]
    snapshot = _snapshot(index="used", manifest=manifest, dispatches=dispatches)
    before = _text(snapshot)
    manifest["selected"][0]["path"] = "changed.py"
    dispatches.append((99, 100))
    assert _text(snapshot) == before and "pkg/a.py" in before


def test_todays_denials_sanitizing_and_escaping_apply_to_every_recorded_value():
    manifest = {"selected": [{"path": ".env", "symbol": "TOKEN", "disclosure": "body", "ranks": {}},
                             {"path": "docs/a_*b*.md", "symbol": "[click](http://x)", "disclosure": "signature", "ranks": {}}]}
    text = _raw(_snapshot(index="used", manifest=manifest), admits=lambda path: path != ".env",
                sanitize=lambda value: value.replace("TOKEN", "[secret]"))

    assert f"- 1. {_plain(why.WITHHELD)}: body" in _plain(text) and ".env" not in _plain(text) and "TOKEN" not in text, "a file refused now is withheld with its symbol"
    assert "docs/a\\_\\*b\\*\\.md" in text and "\\[click\\]\\(http\\[:\\]//x\\)" in text, "Markdown and links render inert"


def test_missing_facts_say_unavailable_and_a_failed_memory_read_is_not_no_memory():
    text = _text(_snapshot(contexts=None, dispatches=None, memory_read="timeout"))
    assert "prepared context: unavailable" in text and "model requests sent: unavailable" in text and "index pack: unavailable" in text
    assert "planning reads: unavailable" in text
    assert "the store's read ended with timeout, so whether memory exists is unknown" in text
    assert "not read before this turn ended" in _text(_snapshot(memory_read="not read"))
    assert "none this turn (no memory store)" in _text(_snapshot())


def test_served_memory_is_identified_by_id_and_version_only():
    item = SimpleNamespace(item="m-0123456789abcdef", version=2, statement="Never push to main.", title="push rule")
    served = memory_serving.ServedSet((item,), (), omitted_optional=1, complete=False, watermarks=("1-0",))  # type: ignore[arg-type]
    text = _text(_snapshot(served=served, memory_read="served"))
    assert "served: m-0123456789abcdef@2" in text and "read: partial; left out: 0 yours, 1 agent lessons" in text
    assert "Never push" not in text and "push rule" not in text


def test_no_snapshot_and_a_later_refusal_are_said_explicitly():
    assert _text(None) == why.NO_SNAPSHOT
    assert _text(None, on_disk=True) == f"{why.NO_SNAPSHOT} {why.NO_SNAPSHOT_ON_DISK}"
    assert _text(_snapshot(turn_seq=4), refused=True).startswith("A later prompt was refused before its context was prepared, so this still explains turn 4.")


def test_pages_are_bounded_deterministic_and_lose_no_entry():
    manifest = {"selected": [{"path": f"pkg/module_{number:03}.py", "symbol": f"name_{number}", "disclosure": "body",
                              "ranks": {"lexical": number}, "reason": "matched " + "x" * (number % 7) * 40} for number in range(300)]}
    snapshot = _snapshot(index="used", manifest=manifest)
    shown = [_plain(page) for page in why.pages(snapshot, sanitize=lambda text: text, admits=lambda path: True)]

    assert len(shown) > 2 and shown == [_plain(page) for page in why.pages(snapshot, sanitize=lambda text: text, admits=lambda path: True)]
    for number, page in enumerate(shown, start=1):
        body = page.split("\n")[1:]
        if number < len(shown):
            assert body[-1] == f"Page {number} of {len(shown)}. `/why {number + 1}` shows the next page."
            body = body[:-2]
        assert len(why.pages(snapshot, sanitize=lambda text: text, admits=lambda path: True)[number - 1].encode("utf-8")) <= why.MAX_PAGE_BYTES and len([line for line in body if line]) <= why.MAX_ENTRIES
    joined = "\n".join(shown)
    assert all(f"pkg/module_{number:03}.py" in joined for number in range(300)) and "[cut:" not in joined
    assert _text(snapshot, len(shown) + 1) == f"The explanation has {len(shown)} page(s); `/why {len(shown)}` shows the last."


def test_one_entry_longer_than_a_page_is_cut_with_a_marker():
    snapshot = _snapshot(index="used", manifest={"selected": [{"path": "a.py", "disclosure": "body", "ranks": {}, "reason": "y" * 20000}]})
    shown = why.pages(snapshot, sanitize=lambda text: text, admits=lambda path: True)
    assert all(len(page.encode("utf-8")) <= why.MAX_PAGE_BYTES for page in shown)
    assert sum("bytes is more than a page]" in page for page in shown) == 1


# --- the ACP host ------------------------------------------------------------------------------------------------------


class _ReportingRunner(Runner):
    """Reports what a production run reports: its automatic context, each request it sends and its planning progress."""

    def __init__(self, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.root = root

    def run(self, request, **kwargs):
        packer, observer = kwargs.get("context_packer"), kwargs.get("planning_progress_observer")
        if packer is not None and not request.approval.approved:
            context = assemble_workspace_context_for_prompt(self.root, task=request.selection_text or request.task)
            packer.record_context(context)
            if context.blocking_stop_reason is not None:
                return AgentRunResult(run_id=request.run_id, session_id=request.session_id, execution_mode=request.execution_mode,
                                      status=AgentRunStatus.FAILED, final_state="FAILED", output_text=context.blocking_message or "stopped",
                                      stop_reason=context.blocking_stop_reason)
            packer.record_dispatch("x" * 400)
            if observer is not None:
                observer(PlanningProgressEvent(run_id=request.run_id, settled_turn=1, max_planning_turns=3, read_request_count=2, read_byte_counts=(30, 12),
                                         read_identities=("pkg/app.py#bytes=0:30", "pkg/app.py#bytes=30:42"), source_sha256s=("a" * 64, "a" * 64)))
        return super().run(request, **kwargs)


async def _host(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text(BODY_MARKER + "\n", encoding="utf-8")
    runner = _ReportingRunner(tmp_path)
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment(), runner)
    return adapter, outbound, runner


@pytest.mark.parametrize("mode", ["agent", "chat"])
async def test_why_answers_from_the_last_turn_without_a_model_call_or_a_conversation_record(tmp_path, mode):
    adapter, outbound, runner = await _host(tmp_path)
    session_id = await new_session(adapter, tmp_path, mode=mode)
    assert (await prompt(adapter, outbound, session_id, "/why", "w0"))["result"]["stopReason"] == "end_turn"
    assert _plain(texts(outbound)[-1]) == why.NO_SNAPSHOT and runner.requests == []

    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p1", approve=mode == "agent")
    calls, records = len(runner.requests), len(session_of(adapter, session_id).conversation.records)

    await prompt(adapter, outbound, session_id, "/why", "w1")

    answer = _plain(texts(outbound)[-1])
    assert answer.startswith(f"Context explanation for turn 1 of this session (run {session_id}:1), page 1 of 1:")
    assert "prepared context: 1 time(s)" in answer and "required: pkg/app.py" in answer
    assert "model requests sent: 1; planning rounds: 1" in answer and "planning reads: 2, returning 42 bytes" in answer
    assert BODY_MARKER not in answer and "never shown" not in answer
    assert len(runner.requests) == calls and len(session_of(adapter, session_id).conversation.records) == records


async def test_the_latest_terminal_attempt_replaces_its_predecessor_even_when_it_was_blocked(tmp_path):
    adapter, outbound, _runner = await _host(tmp_path)
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "dup.py").write_text("x = 1\n", encoding="utf-8")
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p1")
    await prompt(adapter, outbound, session_id, "explain dup.py", "p2")

    await prompt(adapter, outbound, session_id, "/why", "w1")

    answer = _plain(texts(outbound)[-1])
    assert "for turn 2 of this session" in answer and "stop: AMBIGUOUS_WORKSPACE_REFERENCE" in answer
    assert "dup.py was ambiguous, so nothing was chosen" in answer and "never dispatched" in answer


async def test_commands_and_refusals_before_preparation_never_replace_the_snapshot(tmp_path):
    adapter, outbound, _runner = await _host(tmp_path)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p1")
    await prompt(adapter, outbound, session_id, "/why 7", "w1")  # a command, answered and not a turn
    await rpc(adapter, {"jsonrpc": "2.0", "id": "e1", "method": "session/prompt", "params": {"sessionId": session_id, "prompt": []}})

    await prompt(adapter, outbound, session_id, "/why", "w2")

    answer = _plain(texts(outbound)[-1])
    assert answer.startswith("A later prompt was refused before its context was prepared, so this still explains turn 1.")
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p2")
    await prompt(adapter, outbound, session_id, "/why", "w3")
    assert _plain(texts(outbound)[-1]).startswith("Context explanation for turn 2 of this session")


async def test_each_session_explains_only_its_own_turns(tmp_path):
    adapter, outbound, _runner = await _host(tmp_path)
    first, second = await new_session(adapter, tmp_path, mode="chat"), await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, first, "explain pkg/app.py", "p1")

    await prompt(adapter, outbound, second, "/why", "w1")

    assert _plain(texts(outbound)[-1]) == why.NO_SNAPSHOT


async def test_why_is_advertised_without_any_memory_or_usage_store(tmp_path):
    adapter, outbound, _runner = await _host(tmp_path)
    response = await rpc(adapter, {"jsonrpc": "2.0", "id": "n", "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}})
    await adapter.after_response("session/new", response)
    adverts = [n["params"]["update"]["availableCommands"] for n in outbound.notifications
               if n["params"]["update"]["sessionUpdate"] == "available_commands_update"]
    assert adverts == [[{"name": "why", "description": why.DESCRIPTION, "input": {"hint": why.HINT}}]]


async def test_a_cancel_while_the_prompt_finds_its_names_answers_nothing(tmp_path, monkeypatch):
    adapter, outbound, _runner = await _host(tmp_path)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p1")
    shown = len(texts(outbound))
    gate = asyncio.Event()
    real = asyncio.to_thread

    async def slow(function, *args, **kwargs):
        if getattr(function, "__name__", "") == "workspace_names":
            await gate.wait()
        return await real(function, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", slow)
    request = asyncio.create_task(rpc(adapter, {"jsonrpc": "2.0", "id": "w1", "method": "session/prompt",
                                                "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "/why"}]}}))
    await asyncio.sleep(0.05)
    await adapter.handle_client_notification({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session_id}})
    gate.set()

    assert (await asyncio.wait_for(request, 5))["result"]["stopReason"] == "cancelled" and len(texts(outbound)) == shown


def test_the_snapshot_records_actual_facts_not_a_disk_manifest(tmp_path):
    """Disk-write failure never defeats the RAM explanation: the snapshot copies the turn's manifest, not a file."""
    manifest = {"selected": [{"path": "pkg/a.py", "disclosure": "body", "ranks": {}}]}
    snapshot = _snapshot(index="used", manifest=manifest)
    assert json.loads(snapshot.manifest or "{}") == manifest
    assert not list(tmp_path.iterdir())


def _memory_host(tmp_path: Path, session: Any, runner: Any) -> tuple[Any, Any]:
    from tests.unit.acp.test_memory_wiring import _adapter

    return _adapter(tmp_path, lambda workspace: session, runner=runner)


async def test_an_index_turn_is_explained_from_its_own_manifest_and_a_silent_index_says_so(tmp_path):
    from tests.unit.acp.test_memory_wiring import FakeSession, MemoryRunner

    def record(memory: Any) -> None:
        memory.manifest = {"selected": [{"path": "pkg/app.py", "symbol": "main", "disclosure": "body", "ranks": {"lexical": 1}, "reason": "named"}],
                           "budget": {"tokens": 10, "budget_tokens": 4096}, "retrieval": {"state": "ok", "generation": 5}, "grounding": None}

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
    adapter, outbound = _memory_host(tmp_path, FakeSession(), MemoryRunner(record))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await rpc(adapter, {"jsonrpc": "2.0", "id": "p1", "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]}})
    await prompt(adapter, outbound, session_id, "/why", "w1")
    answer = _plain(texts(outbound)[-1])
    assert "context index: used" in answer and "- 1. pkg/app.py main: body; ranks: lexical 1; named" in answer and "generation 5" in answer

    class Silent(FakeSession):
        def turn(self, *, cancelled: Any) -> Any:
            raise RuntimeError("no answer")

    adapter, outbound = _memory_host(tmp_path / "s", Silent(), MemoryRunner())
    (tmp_path / "s").mkdir()
    session_id = await new_session(adapter, tmp_path / "s", mode="chat")
    await rpc(adapter, {"jsonrpc": "2.0", "id": "p1", "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "hi"}]}})
    await prompt(adapter, outbound, session_id, "/why", "w1")
    assert "context index: not answering" in _plain(texts(outbound)[-1])


async def test_a_turn_whose_run_raised_is_still_explained_as_failed(tmp_path):
    class Raising(_ReportingRunner):
        def run(self, request, **kwargs):
            kwargs["context_packer"].record_context(assemble_workspace_context_for_prompt(self.root, task=request.task))
            raise RuntimeError("the run broke")

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "app.py").write_text("x = 1\n", encoding="utf-8")
    adapter, outbound, _runner = make_adapter(tmp_path, make_attachment(), Raising(tmp_path))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    with pytest.raises(RuntimeError):
        await rpc(adapter, {"jsonrpc": "2.0", "id": "p1", "method": "session/prompt", "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "explain pkg/app.py"}]}})

    await prompt(adapter, outbound, session_id, "/why", "w1")

    answer = _plain(texts(outbound)[-1])
    assert "for turn 1 of this session" in answer and "- outcome: failed" in answer and "required: pkg/app.py" in answer


async def test_a_capture_that_fails_leaves_no_stale_explanation_and_logs_a_fixed_line(tmp_path, monkeypatch, caplog):
    adapter, outbound, _runner = await _host(tmp_path)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p1")

    def broken(**fields: Any) -> why.Snapshot:
        raise ValueError(BODY_MARKER)

    monkeypatch.setattr(why, "capture", broken)
    await prompt(adapter, outbound, session_id, "explain pkg/app.py", "p2")

    assert session_of(adapter, session_id).why is None, "turn 1's explanation must not stand in for turn 2"
    assert "context explanation not recorded for this turn" in caplog.text and BODY_MARKER not in caplog.text
