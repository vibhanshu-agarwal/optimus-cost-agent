"""Plan 12.10 Task 3: the worker on real files, real Git and the released dedicated Redis, through the real Gateway route.

Selected with `-m requires_plan12_index_redis`. The embedder is a deterministic stand-in except where a test says otherwise: these
tests are about coherence, isolation and recovery, and the artifact has its own proof.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import redis

from context_engine import index_worker
from context_engine.code_index import path_id
from context_engine.index_worker import IndexWorker, StorageRefusedError, StorageUnavailableError
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.memory_workspace import GatewayIndexStorage, WorkspaceIndexSource, current_branch, index_scope
from optimus.context.project_registry import ProjectRegistration
from optimus.guardrails.file_policy import FilePolicy
from optimus_gateway import memory_index
from optimus_gateway.models import GatewayServiceConfig
from optimus_gateway.server import serve_gateway
from tests.integration.context.conftest import CONTAINER, Provisioned, docker

pytestmark = [pytest.mark.requires_plan12_index_redis]

_SECRET = "index-worker-secret"  # pragma: allowlist secret - synthetic test fixture
_DIMENSIONS = 8


class StubEmbedder:
    identity = "stub-embedding"
    dimensions = _DIMENSIONS

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: Sequence[str]) -> list[bytes]:
        self.calls += len(texts)
        return [struct.pack(f"<{_DIMENSIONS}f", *hashlib.sha256(text.encode()).digest()[:_DIMENSIONS]) for text in texts]


@pytest.fixture(scope="module")
def client(provisioned: Provisioned) -> Iterator[redis.Redis]:
    connection = provisioned.connect()
    yield connection
    connection.close()


def _serve(client: redis.Redis, *, port: int = 0) -> tuple[Any, threading.Thread]:
    store = memory_index.IndexStore(client, cursor_key=b"c" * 32)
    config = GatewayServiceConfig(bind_host="127.0.0.1", bind_port=port, shared_secret=_SECRET, provider="openrouter",
                                  provider_api_key="sk-or-test",  # pragma: allowlist secret - synthetic test fixture
                                  base_url="http://127.0.0.1:9/api/v1")
    server = serve_gateway(config=replace(config, memory_index=memory_index.IndexService(store)), upstream_client=object())  # type: ignore[arg-type]
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    return server, thread


def _settings_for(server: Any) -> OptimusGatewaySettings:
    return OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": f"http://127.0.0.1:{server.server_address[1]}", "OPTIMUS_API_KEY": _SECRET})


def _stop(server: Any, thread: threading.Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(5)


@pytest.fixture
def settings(client: redis.Redis) -> Iterator[OptimusGatewaySettings]:
    server, thread = _serve(client)
    yield _settings_for(server)
    _stop(server, thread)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], capture_output=True, text=True, check=True).stdout


def _repository(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q", "-b", "main")
    (root / "first.py").write_text("def first_function():\n    return 1\n", encoding="utf-8")
    (root / "second.py").write_text("class SecondThing:\n    def method_two(self):\n        return 2\n", encoding="utf-8")
    (root / "notes.md").write_text("# Heading\nSome allowed prose.\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "one")
    return root


class Index:
    """One workspace's real host-side wiring."""

    def __init__(self, root: Path, settings: OptimusGatewaySettings, *, project: str = "project-a", owner: str | None = None) -> None:
        self.root = root
        registration = ProjectRegistration(project, 1, f"git:{project}", str(root), created=False)
        self.scope = index_scope(registration, branch=current_branch(root), embedding=StubEmbedder.identity, parser_version="test")
        self.storage = GatewayIndexStorage(settings, scope=self.scope)
        self.embedder = StubEmbedder()
        self.owner = owner or hashlib.sha256(str(root).encode()).hexdigest()[:32]
        self.priority: Sequence[str] = ()

    def worker(self, **kwargs: Any) -> IndexWorker:
        return IndexWorker(WorkspaceIndexSource(FilePolicy(self.root)), self.storage, self.embedder, owner=self.owner, cold_admission=False,
                           priority=lambda: self.priority, **kwargs)

    def build(self, **kwargs: Any) -> Any:
        return self.worker(**kwargs).run(threading.Event())

    def paths(self, **fields: Any) -> list[str]:
        return sorted(item["path"] for item in self.storage.call("catalogue", **fields)["files"])

    def find(self, term: str, **fields: Any) -> list[dict[str, Any]]:
        return self.storage.call("query", mode="lexical", terms=[term], k=20, **fields)["records"]

    def symbols(self, term: str, **fields: Any) -> list[str]:
        return sorted(record["symbol"] for record in self.find(term, kinds=["symbol"], **fields))


@pytest.fixture
def index(tmp_path: Path, settings: OptimusGatewaySettings) -> Index:
    return Index(_repository(tmp_path / "repo"), settings)


def test_a_full_pass_publishes_every_eligible_file(index: Index) -> None:
    outcome = index.build()
    assert outcome.state == "complete", outcome
    assert index.paths() == ["first.py", "notes.md", "second.py"]
    assert index.symbols("first_function") == ["first_function"]
    assert index.symbols("method_two") == ["SecondThing", "SecondThing.method_two"]  # a class's own terms name its methods
    current = index.storage.call("coverage")["current"]
    assert current["coverage"]["complete"] is True and current["coverage"]["files_indexed"] == 3 and current["dirty"] is False
    assert current["coverage"]["parsed_loc"]["python"] == 5


def test_a_second_pass_embeds_nothing_when_nothing_changed(index: Index) -> None:
    index.build()
    index.embedder.calls = 0
    assert index.build().state == "complete"
    assert index.embedder.calls == 0


def test_the_first_file_is_published_at_once_and_open_files_go_first(index: Index) -> None:
    index.priority = ["second.py"]
    seen: list[list[str]] = []
    real_call = index.storage.call

    def spy(op: str, **fields: Any) -> dict[str, Any]:
        result = real_call(op, **fields)
        if op == "generation" and fields.get("action") == "publish":
            seen.append(index.paths())
            assert result["current"]["coverage"]["complete"] in {False, True}
        return result

    index.storage.call = spy  # type: ignore[method-assign]
    assert index.build().state == "complete"
    assert seen[0] == ["second.py"]
    assert seen[-1] == ["first.py", "notes.md", "second.py"]


def test_the_first_publish_says_it_is_incomplete(index: Index) -> None:
    index.priority = ["first.py"]
    coverages: list[dict[str, Any]] = []
    real_call = index.storage.call

    def spy(op: str, **fields: Any) -> dict[str, Any]:
        if op == "generation" and fields.get("action") == "publish":
            coverages.append(fields["coverage"])
        return real_call(op, **fields)

    index.storage.call = spy  # type: ignore[method-assign]
    index.build()
    assert coverages[0]["complete"] is False and coverages[0]["files_indexed"] == 1 and coverages[0]["files_total"] == 3
    assert coverages[-1]["complete"] is True


def test_an_edit_replaces_only_that_file(index: Index) -> None:
    index.build()
    (index.root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    index.embedder.calls = 0
    assert index.build().state == "complete"
    assert index.embedder.calls == 1
    assert index.symbols("first_function") == []
    assert index.symbols("edited_function") == ["edited_function"]
    assert index.symbols("method_two") == ["SecondThing", "SecondThing.method_two"]


def test_a_reader_pinned_before_an_edit_keeps_its_view(index: Index) -> None:
    index.build()
    pinned = index.storage.call("coverage")["current"]["epoch"]
    (index.root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    # Stop at the first publish, so the old epoch is still retained for its reader.
    real_call = index.storage.call

    def no_prune(op: str, **fields: Any) -> dict[str, Any]:
        return {"status": "ok", "cursor": None} if op == "cleanup" else real_call(op, **fields)

    index.storage.call = no_prune  # type: ignore[method-assign]
    index.build()
    assert index.symbols("first_function", epoch=pinned) == ["first_function"]
    assert index.symbols("edited_function", epoch=pinned) == []


def test_a_deleted_file_leaves_and_a_rename_moves(index: Index) -> None:
    index.build()
    (index.root / "first.py").unlink()
    (index.root / "second.py").rename(index.root / "renamed.py")
    assert index.build().state == "complete"
    assert index.paths() == ["notes.md", "renamed.py"]
    assert index.symbols("first_function") == []
    assert {record["path"] for record in index.find("method_two", kinds=["symbol"])} == {"renamed.py"}


def test_a_file_the_policy_now_excludes_leaves_the_index(index: Index) -> None:
    index.build()
    (index.root / ".optimusignore").write_text("second.py\n", encoding="utf-8")
    assert index.build().state == "complete"
    assert "second.py" not in index.paths()
    assert index.symbols("method_two") == []


def test_an_excluded_file_is_never_read_or_indexed(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    (root / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (root / "ignored.py").write_text("def excluded_name(): pass\n", encoding="utf-8")
    (root / ".env").write_text("API_KEY=x\n", encoding="utf-8")
    index = Index(root, settings)
    index.build()
    assert "ignored.py" not in index.paths() and ".env" not in index.paths()
    assert index.symbols("excluded_name") == []


def test_branches_never_share_a_scope(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    main = Index(root, settings)
    main.build()
    _git(root, "checkout", "-q", "-b", "feature")
    (root / "feature_only.py").write_text("def feature_function():\n    return 1\n", encoding="utf-8")
    feature = Index(root, settings)
    assert feature.scope != main.scope
    feature.build()
    assert feature.symbols("feature_function") == ["feature_function"]
    assert main.symbols("feature_function") == []


def test_worktrees_and_clones_stay_separate(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    _git(root, "worktree", "add", "-q", "-b", "other", str(tmp_path / "wt"))
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(root), str(clone)], check=True)
    first, worktree = Index(root, settings), Index(tmp_path / "wt", settings)
    copied = Index(clone, settings, project="project-clone")
    assert len({first.scope, worktree.scope, copied.scope}) == 3
    (clone / "clone_only.py").write_text("def clone_function(): pass\n", encoding="utf-8")
    copied.build()
    first.build()
    assert first.symbols("clone_function") == []
    assert copied.symbols("clone_function") == ["clone_function"]


def test_a_dirty_tree_is_published_as_dirty_and_a_commit_as_clean(index: Index) -> None:
    index.build()
    clean = index.storage.call("coverage")["current"]
    (index.root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    index.build()
    dirty = index.storage.call("coverage")["current"]
    assert dirty["dirty"] is True and dirty["revision"] != clean["revision"]
    _git(index.root, "add", "-A")
    _git(index.root, "commit", "-q", "-m", "two")
    index.build()
    committed = index.storage.call("coverage")["current"]
    assert committed["dirty"] is False and committed["revision"] not in {clean["revision"], dirty["revision"]}


def test_a_new_file_appears_without_a_rebuild(index: Index) -> None:
    index.build()
    (index.root / "fresh.py").write_text("def new_caller():\n    return first_function()\n", encoding="utf-8")
    index.embedder.calls = 0
    index.build()
    assert index.embedder.calls == 1
    assert sorted(record["symbol"] for record in index.find("first_function", kinds=["symbol"])) == ["first_function", "new_caller"]


def test_cancel_then_resume_finishes_without_repeating_finished_files(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(300):
        (root / f"m{number:03}.py").write_text(f"def function_{number}():\n    return {number}\n", encoding="utf-8")
    index = Index(root, settings)
    cancel = threading.Event()
    real_embed = index.embedder.embed
    embedded = {"n": 0}

    def embed(texts: Sequence[str]) -> list[bytes]:
        embedded["n"] += len(texts)
        if embedded["n"] >= 150:
            cancel.set()
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    first = index.worker().run(cancel)
    assert first.state == "cancelled"
    assert index.storage.call("coverage")["current"]["coverage"]["complete"] is False
    index.embedder.embed = real_embed  # type: ignore[method-assign]
    index.embedder.calls = 0
    second = index.build()
    assert second.state == "complete"
    assert index.embedder.calls < 250  # at most one unsent window is redone
    assert len(index.paths()) == 256  # one page of a catalogue
    assert index.symbols("function_299") == ["function_299"]
    assert index.storage.call("coverage")["current"]["coverage"]["files_indexed"] == 303


_KILLED_WORKER = """
import hashlib, json, os, struct, sys, threading, time
from pathlib import Path
from context_engine.index_worker import IndexWorker
from optimus.config.gateway import OptimusGatewaySettings
from optimus.context.memory_workspace import GatewayIndexStorage, WorkspaceIndexSource
from optimus.guardrails.file_policy import FilePolicy

root, scope, owner, url, key = sys.argv[1:6]
class Embedder:
    identity = "stub-embedding"
    dimensions = 8
    done = 0
    def embed(self, texts):
        Embedder.done += len(texts)
        print(Embedder.done, flush=True)
        if Embedder.done >= 64:
            time.sleep(60)
        return [struct.pack("<8f", *hashlib.sha256(t.encode()).digest()[:8]) for t in texts]
settings = OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": url, "OPTIMUS_API_KEY": key})
IndexWorker(WorkspaceIndexSource(FilePolicy(Path(root))), GatewayIndexStorage(settings, scope=scope), Embedder(), owner=owner, cold_admission=False).run(threading.Event())
"""


def test_a_killed_worker_leaves_nothing_visible_it_did_not_finish_and_a_restart_completes(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(150):
        (root / f"k{number:03}.py").write_text(f"def killed_{number}():\n    return {number}\n", encoding="utf-8")
    index = Index(root, settings)
    child = subprocess.Popen([sys.executable, "-c", _KILLED_WORKER, str(root), index.scope, index.owner, settings.gateway_url, _SECRET],
                             stdout=subprocess.PIPE, text=True)
    assert child.stdout is not None
    for line in child.stdout:
        if int(line) >= 64:
            break
    child.kill()
    child.wait(10)
    held = index.storage.call("coverage")
    assert held["current"] is None or held["current"]["coverage"]["complete"] is False
    assert index.build().state == "complete"
    assert len(index.paths()) == 153
    assert index.symbols("killed_149") == ["killed_149"]
    every = [record["symbol"] for number in (0, 50, 149) for record in index.find(f"killed_{number}", kinds=["symbol"])]
    assert every == ["killed_0", "killed_50", "killed_149"]


def test_a_part_of_a_file_left_by_a_crash_is_not_served_after_the_file_changes(index: Index) -> None:
    index.build()
    token = index.storage.call("lease", action="acquire", owner=index.owner, ttl_ms=30000, kind="scope")["token"]
    epoch = index.storage.call("generation", action="begin", token=token)["epoch"]
    orphan = {"id": "e" * 64, "kind": "symbol", "path": "first.py", "path_id": path_id("first.py"), "file_hash": "f" * 64, "language": "python",
              "symbol": "orphan_symbol", "terms": "orphan_symbol", "vector": base64.b64encode(b"\0" * 32).decode()}
    index.storage.call("batch", token=token, epoch=epoch, records=[orphan])
    index.storage.call("lease", action="release", owner=index.owner, kind="scope", token=token)
    (index.root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    assert index.build().state == "complete"
    assert index.symbols("orphan_symbol") == []


def _interrupted_in_a_big_file(tmp_path: Path, settings: OptimusGatewaySettings) -> Index:
    """One batch of a large file is stored, and then the worker stops, before the file's own record."""
    root = _repository(tmp_path / "repo")
    (root / "big.py").write_text("".join(f"def big_{number}():\n    return {number}\n\n" for number in range(300)), encoding="utf-8")
    index = Index(root, settings)
    index.priority = ["big.py"]
    real_call = index.storage.call
    batches = {"sent": 0}

    def fail_on_the_second_batch(op: str, **fields: Any) -> dict[str, Any]:
        if op == "batch":
            batches["sent"] += 1
            if batches["sent"] == 2:
                raise StorageUnavailableError("gone")
        return real_call(op, **fields)

    index.storage.call = fail_on_the_second_batch  # type: ignore[method-assign]
    assert index.build().state == "paused"
    index.storage.call = real_call  # type: ignore[method-assign]
    return index


def test_a_file_interrupted_between_its_batches_is_redone_whole(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    """A file's own record goes last, so one that exists proves the whole file arrived and a resume may skip it."""
    index = _interrupted_in_a_big_file(tmp_path, settings)
    building = index.storage.call("coverage")["building"]
    assert building is not None and index.paths(epoch=building) == []
    assert index.build().state == "complete"
    assert index.symbols("big_0") == ["big_0"] and index.symbols("big_299") == ["big_299"]


@pytest.mark.parametrize("change", ["deleted", "excluded"])
def test_a_file_interrupted_then_gone_leaves_nothing_published(tmp_path: Path, settings: OptimusGatewaySettings, change: str) -> None:
    index = _interrupted_in_a_big_file(tmp_path, settings)
    if change == "deleted":
        (index.root / "big.py").unlink()
    else:
        (index.root / ".optimusignore").write_text("big.py\n", encoding="utf-8")
    outcome = index.build()
    assert outcome.state == "complete" and outcome.coverage["complete"] is True
    assert index.find("big_0") == [] and index.find("big_299") == []
    assert index.storage.call("catalogue")["unfinished"] == []


def test_a_source_that_moves_during_a_pass_is_not_called_complete(index: Index) -> None:
    real_embed = index.embedder.embed

    def embed(texts: Sequence[str]) -> list[bytes]:
        (index.root / "moved.py").write_text("def moved_function():\n    return 1\n", encoding="utf-8")
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert outcome.state == "paused" and outcome.coverage["complete"] is False
    assert index.storage.call("coverage")["current"]["coverage"]["complete"] is False
    index.embedder.embed = real_embed  # type: ignore[method-assign]
    assert index.build().state == "complete"
    assert index.symbols("moved_function") == ["moved_function"]


@pytest.mark.parametrize("where", ["tracked", "untracked"])
def test_a_further_edit_to_an_already_dirty_file_is_not_called_complete(index: Index, where: str) -> None:
    """Git's status names the path, not its contents, so it reads the same before and after this edit."""
    target = index.root / ("first.py" if where == "tracked" else "new_folder" / Path("late.py"))
    target.parent.mkdir(exist_ok=True)
    target.write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    real_embed = index.embedder.embed
    edited = {"done": False}

    def embed(texts: Sequence[str]) -> list[bytes]:
        vectors = real_embed(texts)
        if not edited["done"]:
            edited["done"] = True
            target.write_text("def edited_again():\n    return 4\n", encoding="utf-8")
        return vectors

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert edited["done"] and outcome.state == "paused" and outcome.coverage["complete"] is False
    index.embedder.embed = real_embed  # type: ignore[method-assign]
    assert index.build().state == "complete"
    assert index.symbols("edited_again") == ["edited_again"]


def test_an_edit_that_keeps_size_and_time_is_not_called_complete(index: Index) -> None:
    """The file is dirty before the pass and again during it, with the same length and a restored time, so nothing but its bytes differ."""
    target = index.root / "first.py"
    target.write_text("def aaaaaaa_function():\n    return 3\n", encoding="utf-8")
    facts = target.stat()
    real_embed = index.embedder.embed
    edited = {"done": False}

    def embed(texts: Sequence[str]) -> list[bytes]:
        vectors = real_embed(texts)
        if not edited["done"]:
            edited["done"] = True
            target.write_text("def bbbbbbb_function():\n    return 3\n", encoding="utf-8")
            os.utime(target, ns=(facts.st_atime_ns, facts.st_mtime_ns))
        return vectors

    index.priority = ["first.py"]
    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert edited["done"] and target.stat().st_mtime_ns == facts.st_mtime_ns
    assert outcome.state == "paused" and outcome.coverage["complete"] is False


def test_a_reader_pinned_across_an_ordinary_pass_is_refused_and_never_answered_partly(index: Index) -> None:
    index.build()
    pinned = index.storage.call("coverage")["current"]["epoch"]
    (index.root / "first.py").write_text("def edited_function():\n    return 3\n", encoding="utf-8")
    assert index.build().state == "complete"
    with pytest.raises(StorageRefusedError) as refused:
        index.find("first_function", epoch=pinned)
    assert refused.value.code == "EPOCH_EXPIRED"
    assert index.symbols("edited_function") == ["edited_function"]


def test_a_borrowed_gateway_that_exits_pauses_the_worker_and_its_return_resumes_it(tmp_path: Path, client: redis.Redis) -> None:
    """The owning host may stop a Gateway another host borrows: no takeover, no new port, and Redis keeps what was published."""
    root = _repository(tmp_path / "repo")
    for number in range(20):
        (root / f"b{number:02}.py").write_text(f"def borrowed_{number}():\n    return {number}\n", encoding="utf-8")
    server, thread = _serve(client)
    index = Index(root, _settings_for(server))
    real_embed = index.embedder.embed
    port = server.server_address[1]
    stopped = {"done": False}

    def embed(texts: Sequence[str]) -> list[bytes]:
        vectors = real_embed(texts)
        if index.embedder.calls >= 3 and not stopped["done"]:
            stopped["done"] = True
            _stop(server, thread)
        return vectors

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert stopped["done"] and outcome.state == "paused", outcome
    with pytest.raises(StorageUnavailableError):
        index.storage.call("coverage")
    index.embedder.embed = real_embed  # type: ignore[method-assign]
    returned, returned_thread = _serve(client, port=port)
    try:
        assert index.build().state == "complete"
        assert len(index.paths()) == 23 and index.symbols("borrowed_19") == ["borrowed_19"]
    finally:
        _stop(returned, returned_thread)


def test_a_competing_worker_is_held_and_changes_nothing(index: Index, settings: OptimusGatewaySettings) -> None:
    other = Index(index.root, settings, owner="cd" * 16)
    index.storage.call("generation", action="open", embedding=StubEmbedder.identity, dimensions=_DIMENSIONS, schema_version=1)
    held_token = other.storage.call("lease", action="acquire", owner=other.owner, ttl_ms=30000, kind="scope")["token"]
    outcome = index.build()
    assert outcome.state == "held" and outcome.detail == "LEASE_HELD"
    assert index.storage.call("coverage")["current"] is None
    other.storage.call("lease", action="release", owner=other.owner, kind="scope", token=held_token)
    assert index.build().state == "complete"


def test_a_worker_that_loses_its_lease_stops_and_its_writes_are_refused(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(200):
        (root / f"l{number:03}.py").write_text(f"def lost_{number}(): pass\n", encoding="utf-8")
    index = Index(root, settings)
    real_embed = index.embedder.embed
    stolen = {"done": False}

    def embed(texts: Sequence[str]) -> list[bytes]:
        if not stolen["done"]:
            stolen["done"] = True
            index.storage.call("lease", action="acquire", owner=index.owner, ttl_ms=30000, kind="scope")  # the same owner resuming elsewhere
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert outcome.state == "held" and outcome.detail == "LEASE_LOST"


def test_a_slow_embedder_does_not_lose_the_lease(tmp_path: Path, settings: OptimusGatewaySettings, monkeypatch: pytest.MonkeyPatch) -> None:
    """A real embedding batch can outlast a lease. The lease must follow the process, not the batches: found by the first real pilot."""
    monkeypatch.setattr(index_worker, "LEASE_MS", 1500)
    monkeypatch.setattr(index_worker, "RENEW_SECONDS", 0.3)
    index = Index(_repository(tmp_path / "repo"), settings)
    real_embed = index.embedder.embed

    def embed(texts: Sequence[str]) -> list[bytes]:
        time.sleep(3.0)
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert outcome.state == "complete", outcome


def test_a_brief_outage_does_not_end_the_lease_heartbeat(tmp_path: Path, settings: OptimusGatewaySettings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(index_worker, "LEASE_MS", 1500)
    monkeypatch.setattr(index_worker, "RENEW_SECONDS", 0.3)
    index = Index(_repository(tmp_path / "repo"), settings)
    real_call, real_embed = index.storage.call, index.embedder.embed
    failed = {"done": False}

    def call(op: str, **fields: Any) -> dict[str, Any]:
        if op == "lease" and fields.get("action") == "renew" and not failed["done"]:
            failed["done"] = True
            raise StorageUnavailableError("a moment")
        return real_call(op, **fields)

    def embed(texts: Sequence[str]) -> list[bytes]:
        time.sleep(3.0)
        return real_embed(texts)

    index.storage.call = call  # type: ignore[method-assign]
    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert failed["done"] and outcome.state == "complete", outcome


def test_resuming_a_partial_cold_build_still_needs_the_cold_slot(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    index = Index(_repository(tmp_path / "a"), settings, project="p-partial")
    other = Index(_repository(tmp_path / "b"), settings, project="p-other")
    real_call = index.storage.call
    publishes = {"n": 0}

    def stop_before_the_last_publish(op: str, **fields: Any) -> dict[str, Any]:
        if op == "generation" and fields.get("action") == "publish":
            publishes["n"] += 1
            if publishes["n"] == 2:
                raise StorageUnavailableError("gone")
        return real_call(op, **fields)

    index.storage.call = stop_before_the_last_publish  # type: ignore[method-assign]
    assert index.build().state == "paused"
    index.storage.call = real_call  # type: ignore[method-assign]
    assert index.storage.call("coverage")["current"]["coverage"]["complete"] is False
    token = other.storage.call("lease", action="acquire", owner=other.owner, ttl_ms=30000, kind="cold")["token"]
    worker = IndexWorker(WorkspaceIndexSource(FilePolicy(index.root)), index.storage, index.embedder, owner=index.owner)
    outcome = worker.run(threading.Event())
    other.storage.call("lease", action="release", owner=other.owner, kind="cold", token=token)
    assert outcome.state == "held" and outcome.detail == "LEASE_HELD"


def test_a_worker_that_loses_the_cold_slot_stops(tmp_path: Path, settings: OptimusGatewaySettings, client: redis.Redis, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(index_worker, "RENEW_SECONDS", 0.1)
    root = _repository(tmp_path / "repo")
    for number in range(40):
        (root / f"c{number:02}.py").write_text(f"def cold_{number}():\n    return {number}\n", encoding="utf-8")
    index = Index(root, settings)
    real_embed = index.embedder.embed

    def embed(texts: Sequence[str]) -> list[bytes]:
        client.set("oidx:lease:cold", "1:" + "cd" * 16, px=5000)  # a stranger now holds the machine's slot
        time.sleep(0.3)
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    worker = IndexWorker(WorkspaceIndexSource(FilePolicy(root)), index.storage, index.embedder, owner=index.owner)
    outcome = worker.run(threading.Event())
    client.delete("oidx:lease:cold")
    assert outcome.state == "held" and outcome.detail == "LEASE_LOST"


def test_only_one_workspace_cold_builds_at_a_time(tmp_path: Path, settings: OptimusGatewaySettings) -> None:
    first, second = Index(_repository(tmp_path / "a"), settings, project="p-a"), Index(_repository(tmp_path / "b"), settings, project="p-b")
    token = first.storage.call("lease", action="acquire", owner=first.owner, ttl_ms=30000, kind="cold")["token"]
    worker = IndexWorker(WorkspaceIndexSource(FilePolicy(second.root)), second.storage, second.embedder, owner=second.owner)
    outcome = worker.run(threading.Event())
    assert outcome.state == "held" and outcome.detail == "LEASE_HELD"
    first.storage.call("lease", action="release", owner=first.owner, kind="cold", token=token)
    assert IndexWorker(WorkspaceIndexSource(FilePolicy(second.root)), second.storage, second.embedder, owner=second.owner).run(threading.Event()).state == "complete"


def test_an_outage_pauses_the_worker_and_a_later_pass_completes(tmp_path: Path, settings: OptimusGatewaySettings, provisioned: Provisioned) -> None:
    root = _repository(tmp_path / "repo")
    for number in range(50):
        (root / f"o{number:02}.py").write_text(f"def outage_{number}(): pass\n", encoding="utf-8")
    index = Index(root, settings)
    real_embed = index.embedder.embed
    killed = {"done": False}

    def embed(texts: Sequence[str]) -> list[bytes]:
        if not killed["done"]:
            killed["done"] = True
            docker("kill", CONTAINER, check=True)
        return real_embed(texts)

    index.embedder.embed = embed  # type: ignore[method-assign]
    outcome = index.build()
    assert outcome.state == "paused"
    index.embedder.embed = real_embed  # type: ignore[method-assign]
    docker("start", CONTAINER, check=True)
    client = provisioned.connect()
    deadline = time.monotonic() + 30
    while True:
        try:
            client.ping()
            break
        except redis.RedisError:
            assert time.monotonic() < deadline
            time.sleep(0.5)
    assert index.build().state == "complete"
    assert len(index.paths()) == 53


def test_an_unreachable_route_is_a_pause_and_not_a_crash(tmp_path: Path) -> None:
    root = _repository(tmp_path / "repo")
    settings = OptimusGatewaySettings.from_env({"OPTIMUS_GATEWAY_URL": "http://127.0.0.1:9", "OPTIMUS_API_KEY": _SECRET})
    index = Index(root, settings)
    with pytest.raises(StorageUnavailableError):
        index.storage.call("coverage")
    assert index.build().state == "paused"


def test_nothing_in_the_store_needs_a_source_body(index: Index, client: redis.Redis) -> None:
    index.build()
    current = json.dumps(index.storage.call("coverage"))
    assert "return 1" not in current
    assert b"return 1" not in b"".join(client.hget(key, "signature") or b"" for key in client.scan_iter(match=f"oidx:rec:8:{index.scope}:*", count=1000))
