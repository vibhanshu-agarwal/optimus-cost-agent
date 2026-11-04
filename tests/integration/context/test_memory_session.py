"""Plan 12.10 Task 4: one session's worker, a turn's context and the four tools on real files, real Git and the released dedicated
Redis, through the real Gateway route.

Selected with `-m requires_plan12_index_redis`. The embedder is a deterministic stand-in except in the one test that says otherwise.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest
import redis

from context_engine.index_worker import StorageRefusedError
from optimus.acp.memory_setup import run_setup, shipped_defaults
from optimus.agent.directives import IndexToolRequest
from optimus.agent.index_turn import run_index_tools
from optimus.agent.tools import AgentToolbox
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context import memory_session
from optimus.context.memory_session import MemorySession, session_factory
from optimus.context.memory_workspace import GatewayIndexStorage
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails.file_policy import FilePolicy
from optimus.runtime.modes import ExecutionMode
from optimus.runtime.state import RuntimeContext
from optimus_security.memory_index_config import memory_index_root, read
from tests.integration.context.conftest import CONTAINER, Provisioned, docker
from tests.integration.context.test_memory_worker import StubEmbedder, _git, _repository, _serve, _settings_for, _stop
from tests.unit.acp.conftest import FakeKeyring
from tests.unit.acp.test_context_engine_admission import new_session
from tests.unit.acp.test_memory_wiring import MemoryRunner, _adapter, _chat, _updates

pytestmark = [pytest.mark.requires_plan12_index_redis]

_BODY_CANARY = "body_canary_value"
_FIRST = f"def first_function():\n    return '{_BODY_CANARY}'\n"


@pytest.fixture(scope="module")
def client(provisioned: Provisioned) -> Iterator[redis.Redis]:
    connection = provisioned.connect()
    yield connection
    connection.close()


@pytest.fixture
def settings(client: redis.Redis) -> Iterator[OptimusGatewaySettings]:
    server, thread = _serve(client)
    yield _settings_for(server)
    _stop(server, thread)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    repository = _repository(tmp_path / "repo")
    (repository / "first.py").write_text(_FIRST, encoding="utf-8")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-q", "-m", "two")
    return repository


def _until(condition: Callable[[], Any], *, seconds: float = 30.0) -> Any:
    deadline = time.monotonic() + seconds
    while True:
        value = condition()
        if value:
            return value
        assert time.monotonic() < deadline, "the condition never held"
        time.sleep(0.05)


class _Sessions:
    """Every session a test opens, each closed at its end so no worker outlives it."""

    def __init__(self, settings: OptimusGatewaySettings, manifests: Path) -> None:
        self.settings = settings
        self.manifests = manifests
        self.opened: list[MemorySession] = []

    def open(self, root: Path, *, embedder: Any = None, wrap: Callable[[Any], Any] = lambda storage: storage, project: str | None = None, prepare: Callable[[MemorySession], None] = lambda _session: None) -> MemorySession:
        name = project or f"project-{root.parent.name}"
        session = MemorySession(
            policy=FilePolicy(root), registration=ProjectRegistration(name, 1, f"git:{name}", str(root), created=False),
            storage_for=lambda scope: wrap(GatewayIndexStorage(self.settings, scope=scope)), embedder_for=lambda: embedder or StubEmbedder(),
            embedding_identity=StubEmbedder.identity, parser_version="test", manifest_root=self.manifests,
        )
        self.opened.append(session)
        prepare(session)
        session.start()
        return session


@pytest.fixture
def sessions(settings: OptimusGatewaySettings, tmp_path: Path) -> Iterator[_Sessions]:
    opened = _Sessions(settings, tmp_path / "manifests")
    yield opened
    for session in opened.opened:
        session.close()


def _ready(session: MemorySession) -> None:
    _until(lambda: session.status().startswith("Context index: ready"))


def _assemble(turn: Any, task: str, *, run_id: str = "run-1", usable: int = 40_000) -> Any:
    return turn.assemble(run_id=run_id, task=task, selection_text=task, model_id="m", estimate=len, usable_input_tokens=usable)


def test_a_session_builds_and_a_turn_gets_verified_excerpts_with_its_scope(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    result = _assemble(session.turn(), "how does first_function work")
    assert _BODY_CANARY in result.text
    assert "complete, 3 of 3 files" in result.text and "covers only this scope" in result.text
    assert "lexical 0 results" not in result.text and "refused" not in result.text and "unavailable" not in result.text


def test_a_turn_writes_no_body_to_its_manifest_or_the_store(root: Path, sessions: _Sessions, client: redis.Redis) -> None:
    session = sessions.open(root)
    _ready(session)
    assert _BODY_CANARY in _assemble(session.turn(), "how does first_function work").text
    manifest = next(sessions.manifests.rglob("run-1.json")).read_text(encoding="utf-8")
    assert json.loads(manifest)["retrieval"]["state"] == "ok" and _BODY_CANARY not in manifest
    keys = list(client.scan_iter(match="oidx:rec:*", count=1000))
    assert keys
    assert not any(_BODY_CANARY.encode() in value for key in keys for value in client.hgetall(key).values())


def test_each_tool_answers_through_the_real_route(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    tools = session.turn().tools
    assert "first.py:" in tools.run("SEARCH", "first_function") and "complete, 3 of 3 files" in tools.run("SEARCH", "first_function")
    assert f"first.py:2: return '{_BODY_CANARY}'" in tools.run("SEARCH", f'"{_BODY_CANARY}"')
    assert "SecondThing.method_two" in tools.run("OUTLINE", "second.py")
    assert "second.py:" in tools.run("SYMBOLS", "SecondThing")
    assert "first.py" in tools.run("LIST", ".")


@pytest.mark.parametrize("words", ["SecondThing METHOD_TWO", "second.py line:3", "what's in (first)?", "a" * 300, "x" * 40 + " " + "y" * 40, "naïve café"])
def test_what_a_model_may_type_is_never_a_refused_search(root: Path, sessions: _Sessions, words: str) -> None:
    """The route refuses what is not a folded term. A person's or a model's words must never reach it unfolded."""
    session = sessions.open(root)
    _ready(session)
    turn = session.turn()
    assert "could not answer" not in turn.tools.run("SEARCH", words)
    assert "could not answer" not in turn.tools.run("SYMBOLS", words)
    assert "refused" not in _assemble(turn, words).text


@pytest.mark.parametrize("task", ["look at SecondThing.method_two", "does `first_function` call parseThing", "see a.b.c.d.e and x_y"])
def test_a_named_symbol_reaches_the_route_in_a_form_it_accepts(root: Path, sessions: _Sessions, task: str) -> None:
    session = sessions.open(root)
    _ready(session)
    assert "structure refused" not in _assemble(session.turn(), task).text


def test_an_unsaved_buffer_never_reaches_the_store(root: Path, sessions: _Sessions, client: redis.Redis) -> None:
    session = sessions.open(root)
    _ready(session)
    turn = session.turn()
    turn.read_buffer = lambda path: "def unsaved_canary_name():\n    return 'unsaved_canary_value'\n"
    assert "unsaved_canary_value" in _assemble(turn, "explain first.py").text
    assert "unsaved_canary_name" in turn.tools.run("OUTLINE", "first.py")
    session.request_pass()
    _until(lambda: session._last_outcome is not None and session._last_outcome.state == "complete")
    assert "(unsaved)" in turn.tools.run("SYMBOLS", "unsaved_canary_name")
    keys = list(client.scan_iter(match="oidx:rec:*", count=1000))
    assert keys and not any(b"unsaved_canary" in value for key in keys for value in client.hgetall(key).values())


def test_a_partial_build_is_usable_and_says_so_and_a_turn_does_not_wait_for_the_worker(tmp_path: Path, sessions: _Sessions) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(40):
        (root / f"m{number:02}.py").write_text(f"def partial_{number}():\n    return {number}\n", encoding="utf-8")
    hold = threading.Event()
    published = threading.Event()

    class Gated(StubEmbedder):
        def embed(self, texts: Sequence[str]) -> list[bytes]:
            if threading.current_thread().name == "context-index" and self.calls:
                published.set()
                hold.wait(60)
            return super().embed(texts)

    session = sessions.open(root, embedder=Gated())
    try:
        assert published.wait(30)
        status = _until(lambda: (line := session.status()) if "building, " in (line := session.status()) and "nothing" not in line else None)
        assert " of 43 files" in status
        started = time.monotonic()
        result = _assemble(session.turn(), "where is partial_1")
        assert time.monotonic() - started < 10
        assert "still building" in result.text and "covers only this scope" in result.text
        assert "still building" in session.turn().tools.run("SYMBOLS", "no_such_symbol")
        assert session.turn().ground("`no_such_symbol`").unresolved == ()  # absence is not provable during a build
    finally:
        hold.set()
    _ready(session)


def test_an_edit_is_reconciled_and_the_old_body_is_never_shown(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    (root / "first.py").write_text("def first_function():\n    return 'edited_body_value'\n", encoding="utf-8")
    result = _assemble(session.turn(), "how does first_function work")
    assert _BODY_CANARY not in result.text
    assert "edited_body_value" in result.text or "incomplete: " in result.text
    _until(lambda: "edited_body_value" in _assemble(session.turn(), "how does first_function work").text)


def test_changing_branch_never_shows_the_other_branchs_records(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    _git(root, "checkout", "-q", "-b", "feature")
    (root / "feature_only.py").write_text("def feature_function():\n    return 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "feature")
    _until(lambda: "feature_only.py:" in session.turn().tools.run("SYMBOLS", "feature_function"))
    _git(root, "checkout", "-q", "main")
    (root / "main_only.py").write_text("def main_function():\n    return 1\n", encoding="utf-8")
    assert "feature_only.py" not in session.turn().tools.run("SYMBOLS", "feature_function")
    assert "feature_only.py" not in _assemble(session.turn(), "where is feature_function").text


def test_a_branch_made_at_the_same_commit_as_a_pass_finishes_still_gets_its_own_line(root: Path, sessions: _Sessions) -> None:
    """Two branches at one commit read as the same revision. A pass ending just after the switch must not stand in for the new line."""
    holder: dict[str, MemorySession] = {}
    switched = threading.Event()

    class SwitchAtPublish:
        def __init__(self, storage: Any) -> None:
            self._storage = storage

        def call(self, op: str, **fields: Any) -> dict[str, Any]:
            reply = self._storage.call(op, **fields)
            if op == "generation" and fields.get("action") == "publish" and reply["current"]["coverage"]["complete"] and not switched.is_set():
                _git(root, "checkout", "-q", "-b", "feature")
                holder["session"]._current_scope()
                switched.set()
            return reply

    holder["session"] = sessions.open(root, wrap=SwitchAtPublish)
    assert switched.wait(30)
    assert "feature" in _git(root, "branch", "--show-current")
    _ready(holder["session"])
    assert "first.py:" in holder["session"].turn().tools.run("SYMBOLS", "first_function")


def test_a_switch_before_a_pass_looks_at_the_disk_never_writes_that_branch_into_this_line(root: Path, sessions: _Sessions, settings: OptimusGatewaySettings) -> None:
    switched = threading.Event()

    def prepare(session: MemorySession) -> None:
        real = session._source.revision

        def switch_then_look() -> tuple[str, bool]:
            if not switched.is_set():
                _git(root, "checkout", "-q", "-b", "feature")
                (root / "feature_only.py").write_text("def feature_function():\n    return 1\n", encoding="utf-8")
                switched.set()
            return real()

        session._source.revision = switch_then_look  # type: ignore[method-assign]

    session = sessions.open(root, prepare=prepare)
    original = session._scope.identity
    assert switched.wait(30)
    _until(lambda: session._scope.identity != original and session.status().startswith("Context index: ready"))
    assert "feature_only.py:" in session.turn().tools.run("SYMBOLS", "feature_function")
    with pytest.raises(StorageRefusedError) as refused:  # the pass wrote nothing: its line was never even opened
        GatewayIndexStorage(settings, scope=original).call("coverage")
    assert refused.value.code == "SCOPE_UNKNOWN"


def test_a_file_made_just_before_the_turn_is_found_when_it_is_named(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    session.listing()
    (root / "brand_new.py").write_text("def brand_new_function():\n    return 'brand_new_body'\n", encoding="utf-8")
    result = _assemble(session.turn(), "explain brand_new.py")
    assert result.blocking_stop_reason is None and "brand_new_body" in result.text and result.prioritized_paths == ("brand_new.py",)


def test_a_tool_sees_a_file_made_after_the_last_walk(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    session.listing()
    turn = session.turn()
    (root / "just_made.py").write_text("def just_made():\n    return 'just_made_value'\n", encoding="utf-8")
    assert "just_made.py" in turn.tools.run("LIST", ".")
    assert "just_made_value" in turn.tools.run("SEARCH", '"just_made_value"')


def test_a_file_written_during_a_turn_is_not_reported_as_missing(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    turn = session.turn()
    (root / "written_now.py").write_text("def written_now():\n    return 1\n", encoding="utf-8")
    report = turn.ground("I wrote written_now.py, and gone_entirely.py is cited too.")
    assert "written_now.py" in report.resolved and report.unresolved == ("gone_entirely.py",)


def test_grounding_checks_real_symbols_on_a_complete_index(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    report = session.turn().ground("`first_function` is in first.py but `invented_name` is not.")
    assert set(report.resolved) == {"first.py", "first_function"} and report.unresolved == ("invented_name",)  # the disk is what was published


def test_a_symbol_added_since_the_generation_is_not_called_absent(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    (root / "second.py").write_text("def added_since():\n    return 1\n", encoding="utf-8")
    assert session.turn().ground("`added_since`").unresolved == ()


def test_editing_the_ignore_file_mid_session_takes_effect_at_once_and_leaves_the_index(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    turn = session.turn()
    assert "SecondThing" in turn.tools.run("OUTLINE", "second.py")
    (root / ".optimusignore").write_text("second.py\n", encoding="utf-8")
    assert "cannot be read" in turn.tools.run("OUTLINE", "second.py")
    assert "second.py" not in turn.tools.run("LIST", ".")
    assert "second.py" not in session.turn().repo_map()
    assert "SecondThing" not in _assemble(session.turn(), "how does SecondThing work").text
    _until(lambda: "second.py" not in session._scope.storage.call("catalogue")["files"].__repr__())


def test_a_map_on_real_storage_loses_a_deleted_file_at_once(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    scope = session._current_scope()
    assert "second.py: SecondThing" in session.repo_map(scope)
    (root / "second.py").unlink()
    assert "second.py" not in session.repo_map(scope)


def test_closing_a_session_stops_its_worker_and_frees_the_line_for_the_next(tmp_path: Path, sessions: _Sessions) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(60):
        (root / f"c{number:02}.py").write_text(f"def closing_{number}():\n    return {number}\n", encoding="utf-8")
    started = threading.Event()

    class Slow(StubEmbedder):
        def embed(self, texts: Sequence[str]) -> list[bytes]:
            started.set()
            time.sleep(0.2)
            return super().embed(texts)

    first = sessions.open(root, embedder=Slow(), project="closing")
    assert started.wait(30)
    first.close()
    assert first._thread is not None and not first._thread.is_alive()
    assert first._last_outcome is not None and first._last_outcome.state == "cancelled"
    second = sessions.open(root, project="closing")
    _ready(second)
    assert "first.py" in second.turn().tools.run("LIST", ".")
    _until(lambda: second._last_outcome is not None and second._last_outcome.state == "complete")


def test_a_generation_that_expires_under_a_reader_is_tried_again_and_never_answered_partly(root: Path, sessions: _Sessions) -> None:
    session = sessions.open(root)
    _ready(session)
    storage = session._scope.storage
    current = storage.call("coverage")["current"]
    # A real older epoch that the worker has since pruned, handed out once.
    (root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    session.request_pass()

    def expired() -> bool:
        try:
            storage.call("query", mode="lexical", epoch=current["epoch"], terms=["first_function"], k=1)
        except StorageRefusedError:
            return True
        return False

    _until(expired)  # a publish comes first and the prune after it, so this waits for the prune itself
    real_call = storage.call
    first_look = {"pending": True}

    def stale_once(op: str, **fields: Any) -> dict[str, Any]:
        if op == "coverage" and first_look["pending"]:
            first_look["pending"] = False
            return {"status": "ok", "current": current}
        return real_call(op, **fields)

    storage.call = stale_once  # type: ignore[method-assign]
    turn = session.turn()
    retrieval = turn._retriever.retrieve("edited_function")
    storage.call = real_call  # type: ignore[method-assign]
    assert retrieval.state == "ok" and retrieval.epoch != current["epoch"] and not first_look["pending"]
    assert any(item.hit.symbol == "edited_function" for item in retrieval.ranked)


def test_an_outage_keeps_todays_context_says_so_and_the_session_recovers(root: Path, sessions: _Sessions, provisioned: Provisioned, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(memory_session, "RETRY_SECONDS", 0.5)
    session = sessions.open(root)
    _ready(session)
    docker("kill", CONTAINER, check=True)
    try:
        assert "cannot be reached" in session.status()
        turn = session.turn()
        result = _assemble(turn, "how does first_function work")
        assert result.blocking_stop_reason is None and "no usable generation (unavailable)" in result.text
        assert _BODY_CANARY in result.text  # today's selection reads disk, as it does without an index
        assert "could not answer" in turn.tools.run("SEARCH", "first_function")
        assert "could not answer" in turn.tools.run("SYMBOLS", "first_function")
        assert "first.py" in turn.tools.run("LIST", ".") and "first_function" in turn.tools.run("OUTLINE", "first.py")  # disk still answers
        assert _BODY_CANARY in turn.tools.run("SEARCH", f'"{_BODY_CANARY}"')
    finally:
        docker("start", CONTAINER, check=True)
    connection = provisioned.connect()
    _until(lambda: _pings(connection))
    (root / "after_outage.py").write_text("def after_outage():\n    return 1\n", encoding="utf-8")
    session.request_pass()
    _until(lambda: "after_outage.py:" in session.turn().tools.run("SYMBOLS", "after_outage"), seconds=60)


def test_the_host_drives_a_real_session_through_a_turn(root: Path, sessions: _Sessions) -> None:
    """The adapter's real wiring on the real session, so the two cannot drift apart behind their doubles."""
    session = sessions.open(root)
    _ready(session)
    seen: dict[str, Any] = {}

    def during(memory: Any) -> None:
        seen["context"] = memory.assemble(run_id="host-1", task="how does first_function work", selection_text="how does first_function work", model_id="m", estimate=len, usable_input_tokens=40_000)
        seen["ran"] = run_index_tools((IndexToolRequest("SEARCH", "first_function"), IndexToolRequest("LIST", ".")), memory, AgentToolbox.for_workspace(workspace_root=root, context=RuntimeContext(execution_mode=ExecutionMode.CHAT), run_id="r", session_id="s"), halted=lambda: False)

    async def scenario() -> list[dict[str, Any]]:
        adapter, outbound = _adapter(root, lambda workspace: session, runner=MemoryRunner(during))
        session_id = await new_session(adapter, root, mode="chat")
        assert (await _chat(adapter, session_id, "p1"))["result"]["stopReason"] == "end_turn"
        await asyncio.sleep(0)
        return _updates(outbound)

    updates = asyncio.run(scenario())
    assert _BODY_CANARY in seen["context"].text
    assert [call.authorization_outcome for call in seen["ran"].calls] == ["ALLOW", "ALLOW"]
    assert any("Context index: ready, 3 of 3 files." in str(update) for update in updates)
    titles = [(update["sessionUpdate"], update["title"], update["status"]) for update in updates if update.get("sessionUpdate", "").startswith("tool_call") and update["title"].split(" ")[0] in {"SEARCH", "LIST"}]
    assert titles == [("tool_call", "SEARCH first_function", "in_progress"), ("tool_call_update", "SEARCH first_function", "completed"), ("tool_call", "LIST .", "in_progress"), ("tool_call_update", "LIST .", "completed")]


def _pings(connection: redis.Redis) -> bool:
    try:
        return bool(connection.ping())
    except redis.RedisError:
        return False


def test_the_real_artifact_answers_a_turn_while_its_own_worker_embeds(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    """One loaded model serves the worker's batches and a person's query at once, through the factory a real launch uses."""
    snapshot = os.environ.get("P1210_ARTIFACT_SNAPSHOT")
    if not snapshot or not Path(snapshot).is_dir():
        pytest.skip("UNRUN: P1210_ARTIFACT_SNAPSHOT names no local artifact")

    def copy(*, repository: str, revision: str, target: Path) -> None:
        shutil.copytree(snapshot, target, dirs_exist_ok=True)

    defaults = shipped_defaults()
    config_root = tmp_path / "config"
    run_setup(config_root, keyring_backend=FakeKeyring(), confirm=lambda _description: True, download=copy, defaults=defaults)
    memory_root = memory_index_root(config_root)
    _literal, config, _refusal = read(memory_root)
    assert config is not None
    root = _repository(tmp_path / "repo")
    for number in range(150):
        (root / f"real{number:03}.py").write_text(f"def real_function_{number}(value):\n    \"\"\"Adds {number} to a value.\"\"\"\n    return value + {number}\n", encoding="utf-8")
    session = session_factory(memory_root=memory_root, config_root=config_root, settings=settings, config=config, artifact_directory=defaults["embedding"]["artifact_directory"])(root)
    assert session is not None
    session.start()
    try:
        dense = 0
        answered = _until(lambda: "building, " in session.status() and "nothing" not in session.status(), seconds=120)
        assert answered
        while session.status().startswith("Context index: building"):
            retrieval = session.turn()._retriever.retrieve("add a number to a value")
            assert retrieval.state == "ok", retrieval
            assert retrieval.channels["dense"].endswith("results"), retrieval.channels
            dense += 1
        assert dense >= 3, "the worker finished before enough queries ran alongside it"
        _until(lambda: session._last_outcome is not None and session._last_outcome.state == "complete", seconds=120)
        assert session._unusable is None
    finally:
        session.close()
