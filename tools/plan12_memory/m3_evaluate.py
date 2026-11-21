"""Plan 12.11 Task 5 qualification: `python -m tools.plan12_memory.m3_evaluate --config reports/plan12-memory-m3/run-config.json
--output tmp/plan12-memory-m3`.

Each case is driven through the production host: the real ACP adapter, the host memory commands, the launch's own extractor
factory and the Gateway's memory handler on the released test store (`p1211-cp4-test-redis`). Its trace is built only from what
that run observably did, never from the case's expectations, and every observation is recorded at its own boundary, in the
order it happened (Codex CP4 review 2, F3):

- each Gateway request and its reply, at the host's store client: an append's commit result is bound to its project, request
  and event (F2), and the store's event stream is read right after each reply, so each entry is placed after the request that
  wrote it;
- each memory card and answer the host sends on its ACP channel, as it is sent (a card that cannot be sent, and whether the
  project's durable backlog kept it), and each permission request the host makes;
- the serving decision the host made for each turn (`MemoryCommands.served`), and the block each model request carried;
- each extraction call the stand-in received, and each outcome the extractor reported (skips and refusals included).

One fixed table (`EVENT_OF`) turns those observations into the grader's event names; every name in it has a detector here, so
its absence was observed (F4). A needed name the run cannot observe goes into `missing_coverage`, as does anything the run did
not exercise (a crash without real process loss: F6; earlier versions of an item it never saw: F7), so the case cannot pass.
The models are local stand-ins with zero paid calls: the answer layer, and retrieval of evidence, stay with the released paid
Zed sessions.

Case inputs are natural-language scenarios. A user input is said as written. Every other input names, in the run config, the one
real operation that carries it out (`OPS`): a paused store, a dropped card, a changed file, a git rebase, a clock shift, the
agent's completed work, a lost store volume. Case keys (`pref-indent`) name the item a given case input created, as the run
config declares; a `{key}` or `{key@v}` in a command is the id (and current version) the user would read in `/memory`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import SecretStr

from context_engine import memory_gate
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse
from optimus.context.memory_extraction import AGENT_PURPOSE, CompletedWork, Evidence, TurnInput, UserBlock, extractor_factory
from optimus.runtime.modes import ExecutionMode
from optimus_gateway import memory_store
from tools.plan12_memory.contracts import (
    AnswerObservation,
    GoldenCase,
    MemoryRef,
    MemoryStateObservation,
    ObservedTrace,
    ReportedCost,
    TraceEvent,
)
from tools.plan12_memory.evaluate import grade_trace

SCHEMA = "plan12-memory-m3.qualification-run.v1"
CARD = "memory/"
_REAL_TIME = time.time
# The fixed translation from an observation to the grader's event name. An observation of an item carries that item's case key.
EVENT_OF: Mapping[str, str] = {
    "commit.admit": "memory.committed",  # the Gateway's confirmed result for this project's append of this event
    "commit.update": "memory.committed",
    "store.update": "memory.superseded",
    "store.withdraw": "memory.withdrawn",
    "store.tombstone": "memory.purged",
    "store.off": "memory.candidate.off",
    "store.off.archived": "memory.archived_overflow",
    "store.off.conflict": "memory.conflict.off",  # an append with status conflicted
    "store.off.blocked": "memory.secret_refused",
    "store.trust_changed": "memory.trust_changed",  # an item's append whose trust differs from its previous version's
    "store.trust_promoted": "memory.trust_promoted",  # ... to the user's own trust
    "store.pointer": "memory.pointer_only",
    "store.body": "memory.body_persisted",  # a saved statement holds a workspace file's text
    "card.Remembered": "memory.notice.remembered",
    "card.Updated": "memory.notice.remembered",
    "card.unconfirmed": "memory.notice.unconfirmed",
    "card.backlogged": "memory.notice.backlogged",  # a card that could not be sent, which the project's durable backlog kept
    "answer.unconfirmed": "memory.notice.unconfirmed",  # a user command's own unconfirmed reply, with no model call (review 5)
    "answer.refused_secret": "memory.secret_refused",  # pragma: allowlist secret
    "answer.read_only": "memory.blocked_untrusted_workspace",
    "answer.switched_on": "memory.switched_on",
    "answer.switch_on_unavailable": "memory.switch_on_unavailable",
    "host.prompt": "memory.prompt_user",  # a permission request the user's own command did not ask for
    "served": "memory.served",
    "served.reverify": "memory.reverify",
    "served.expired": "memory.expired",  # a live item the serving decision left out with no stated reason
    "checkpoint": "checkpoint.written",
    "brief.first": "brief.shown.first_response",
    "brief.request": "brief.shown.on_request",
    "brief.resumed": "continuation.resumed",
    "brief.rewritten": "continuation.baseline_rewritten",
    "restore.published": "restore.published",
    "restore.mapped": "restore.rekey_mapped",
    "restore.unmapped": "restore.rekey_unmapped",  # a restore published into another project than the copy's, without a mapping
    "restore.anchor": "restore.anchor_mapped",
    "restore.tombstones": "restore.tombstones_applied",
    "restore.rejected": "restore.mapping_rejected",
    "restore.held": "restore.held_unserved",
    "prompt.from_summary": "memory.extracted_from_summary",
    "store.import": "memory.import.optional",  # an import's admit, as legacy-import (Plan 12.12 Task 2)
    "store.trust_from_import": "memory.trust_from_import",  # any other trust appended while an import applies
}
# Names this harness can observe: when one is absent, the run observed its absence. Any other needed name is missing coverage.
OBSERVABLE = frozenset(EVENT_OF.values())
# Never observable here, with the owner of the evidence (plan v5 Evaluation): reported UNRUN, never PASS.
UNRUN_EVENTS = {"memory.strength_faded": "#235 M6 (decay)", "memory.strength_raised": "#235 M6 (decay)"}
# A decay case's own safety obligations stay with #490 (plan v5): these must not be seen however much time passes.
SAFETY_EVENTS = ("memory.expired", "memory.trust_promoted", "memory.trust_changed")
_LIVE = ("active", "reverify", "conflicted")


@dataclass
class Observation:
    seq: int  # the case input it belongs to
    kind: str  # an EVENT_OF key, or a harness record (extraction calls and outcomes, restore pin results)
    item: str | None = None
    version: int | None = None
    project: str | None = None


@dataclass
class Run:
    """What one case's run observed, in the order it happened."""

    observations: list[Observation] = field(default_factory=list)
    served: list[list[tuple[str, int]]] = field(default_factory=list)  # per model request: (item, version) served
    created_by: dict[tuple[str, str], int] = field(default_factory=dict)  # (project, item) -> the case input that first appended it
    history: dict[tuple[str, str], dict[int, dict[str, Any]]] = field(default_factory=dict)  # (project, item) -> version -> entry seen
    mapped: dict[str, str] = field(default_factory=dict)  # project -> the project a published restore mapped into it
    outcomes: list[dict[str, Any]] = field(default_factory=list)  # each extraction outcome the extractor reported
    calls: list[str] = field(default_factory=list)  # each extraction call the stand-in received: agent, user or summary
    uncovered: list[str] = field(default_factory=list)  # what the run did not exercise, as missing coverage
    answers: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)  # what each input did, for the report
    seq: int = -1  # the case input being carried out
    command: bool = False  # that input is a user command (`/...`)
    requests_at_input: int = 0  # model requests made before that input began
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def add(self, kind: str, item: str | None = None, version: int | None = None, project: str | None = None) -> None:
        with self.lock:
            self.observations.append(Observation(self.seq, kind, item, version, project))


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, name: str) -> str | None:
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.values.pop((service, name), None)


_SERVED_LINE = re.compile(r"^- \[memory:(m-[0-9a-f]{16})@([0-9]+)\]", re.M)


class _Model:
    """The zero-paid stand-in for the session's model: a Chat answer that states no fact, so the answer layer cannot pass here.
    `say_next` makes the next answer a given text (an assistant input of a case). Each request's memory block is recorded as it
    arrives."""

    def __init__(self, run: Run) -> None:
        self.run_record = run
        self.requests: list[Any] = []
        self.say_next: str | None = None

    def run(self, request: Any, **_kwargs: Any) -> AgentRunResult:
        self.requests.append(request)
        served = [(item, int(version)) for item, version in _SERVED_LINE.findall(request.memory_context or "")]
        self.run_record.served.append(served)
        for item, version in served:
            self.run_record.add("served", item, version, getattr(self, "project", None))
        text, self.say_next = self.say_next or "(controlled stand-in answer)", None
        common = dict(run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=())
        return AgentRunResult(execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY",
                              output_text=text, total_cost_usd=Decimal("0"), **common)


class _Extraction:
    """The zero-paid stand-in for the summarizer route. For user extraction it proposes each block whole, as a question when it
    asks one and as a preference otherwise; D9 sends every automatic user proposal off, so its wording never becomes memory. For
    agent extraction it proposes the lessons the case's work queued, each citing the evidence it names (a tool's or document's
    evidence for a hostile lesson, F5), or the first evidence listed. Context summaries get a fixed valid summary. Each call is
    recorded."""

    def __init__(self, run: Run) -> None:
        self.run = run
        self.calls = 0
        self.lessons: list[tuple[str, str | None]] = []

    def __call__(self, *, prompt: str, max_output_tokens: int, purpose: str = "") -> SummarizerResponse:
        self.calls += 1
        attempt = SummarizerAttempt(f"stand-in-{self.calls}", f"gw-stand-in-{self.calls}", "completed", Decimal("0"))
        if "<summary" in prompt or "Summary of earlier" in prompt:
            self.run.add("prompt.from_summary")
        if prompt.startswith("You extract at most a few optional lessons"):
            self.run.calls.append("agent")
            refs = re.findall(r"^- (\S+) \(", prompt, re.M)
            candidates = [{"speech_act": "assertion", "kind": "lesson", "title": text[:60], "statement": text,
                           "evidence": [ref] if ref else refs[:1]} for text, ref in self.lessons]
            self.lessons = []
        elif prompt.startswith("You extract"):
            self.run.calls.append("user")
            candidates = []
            for block, text in re.findall(r'<block id="([^"]+)">(.*?)</block>', prompt, re.S):
                act = "question" if text.rstrip().endswith("?") else "preference"
                candidates.append({"speech_act": act, "kind": "preference", "title": text[:60], "statement": text,
                                   "spans": [{"block": block, "start": 0, "end": len(text)}]})
        else:
            self.run.calls.append("summary")
            from tests.unit.acp.test_context_engine_admission import SUMMARY

            return SummarizerResponse(text=SUMMARY, finish_status="stop", attempts=(attempt,))
        return SummarizerResponse(text=json.dumps({"candidates": candidates}), finish_status="stop", attempts=(attempt,))


class _Channel(RecordingOutboundChannel):
    """The host's ACP channel to its client, recording each memory card, answer and permission request as the host sends it.
    `fail_cards`: the client went away after the commit, so a memory card cannot be sent."""

    def __init__(self, rig: Rig) -> None:
        super().__init__()
        self.rig = rig
        self.host: Host | None = None
        self.fail_cards = False

    async def notify(self, method: str, params: dict[str, Any], **kwargs: Any) -> Any:
        update = params.get("update", {}) if method == "session/update" else {}
        card = update.get("sessionUpdate") == "tool_call" and str(update.get("toolCallId", "")).startswith(CARD)
        if card and self.fail_cards:
            self.rig.card_failed(self.host, update)
            raise ConnectionError("the client went away")
        before = len(self.notifications)
        result = await super().notify(method, params, **kwargs)
        if len(self.notifications) > before:  # delivered (a suppressed progress write is not)
            if card:
                self.rig.card(self.host, update)
            elif update.get("sessionUpdate") == "agent_message_chunk":
                self.rig.answer(self.host, update.get("content", {}).get("text", ""))
        return result

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "session/request_permission" and not self.rig.asking:
            self.rig.run.add("host.prompt", project=self.host.project if self.host else None)
        return await super().request(method, params)


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "m3", "GIT_AUTHOR_EMAIL": "m3@example.invalid", "GIT_COMMITTER_NAME": "m3",
           "GIT_COMMITTER_EMAIL": "m3@example.invalid"}
    return subprocess.run(["git", "-c", "init.defaultBranch=main", "-c", "core.longpaths=true", *args], cwd=cwd, env=env, check=True,
                          capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()


def _new_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    (path / "README.md").write_bytes(b"synthetic qualification workspace\n")
    (path / ".editorconfig").write_bytes(b"indent_style = tab\n")
    (path / "config.py").write_bytes(b"def parse_config():\n    return {}\n")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_bytes(b"def main():\n    return 0\n")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "first")
    return path


class Store:
    """The released test store and the Gateway service on it; `lose_volume` really removes and recreates its volume."""

    def __init__(self, work: Path) -> None:
        from optimus.acp import local_infra
        from tests.integration.memory.conftest import Provisioned, remove_released_resources, setup_config, wait_for_auth

        self.work = work
        remove_released_resources()
        self.root, self.config, self.password = setup_config(work / "store")
        assert local_infra.ensure_memory_store_redis(self.root).state == "ready"
        wait_for_auth(Provisioned(self.root, self.config, self.password))
        self.service = self.gateway(work / "journal")
        self.observer = self._observer()

    def _observer(self) -> Any:
        """A read connection of the harness's own: the Gateway's pool holds one connection, which its own requests use. Only
        the endpoint is copied: the Gateway's connection bookkeeping (`optimus_link`) would count this connection as its own
        reconnect and stop serving."""
        import redis

        kwargs = self.service._store._redis.connection_pool.connection_kwargs
        return redis.Redis(**{name: kwargs[name] for name in ("host", "port", "username", "password")}, protocol=2)

    def gateway(self, journal: Path) -> memory_store.MemoryStoreService:
        keyring = _Keyring()
        keyring.set_password(memory_store.KEYRING_SERVICE, self.config.credential_name, self.password)
        return memory_store.build_memory_store_service(self.config, keyring_backend=keyring, hmac_key=b"m" * 32, journal_root=journal)

    def lose_volume(self) -> None:
        from optimus.acp import local_infra
        from tests.integration.memory.conftest import CONTAINER, VOLUME, Provisioned, docker, wait_for_auth

        docker("rm", "-f", CONTAINER, check=True)
        docker("volume", "rm", "-f", VOLUME, check=True)
        assert local_infra.ensure_memory_store_redis(self.root).state == "ready"
        wait_for_auth(Provisioned(self.root, self.config, self.password))
        self.service = self.gateway(self.work / "journal")  # the same Gateway journal survives a lost volume
        self.observer = self._observer()

    @contextlib.contextmanager
    def paused(self) -> Iterator[None]:
        from tests.integration.memory.conftest import CONTAINER, docker

        docker("pause", CONTAINER, check=True)
        try:
            yield
        finally:
            docker("unpause", CONTAINER, check=True)


class Host:
    """One host process's view: an adapter with its own config root on one workspace, opening one Chat session."""

    def __init__(self, rig: Rig, workspace: Path, config: Path) -> None:
        self.rig, self.workspace, self.config = rig, workspace, config
        self.outbound = _Channel(rig)
        self.outbound.host = self
        settings = SimpleNamespace(optimus_api_key=SecretStr("m3-qualification"))
        factory = extractor_factory(config_root=config, settings=settings, post=rig.post)
        from tests.unit.acp.test_context_engine_admission import make_attachment

        self.adapter = AcpDuplexAdapter(runner=rig.model, workspace_root=workspace, sessions=InMemoryAcpSpecSessionStore(),
                                        outbound=self.outbound, context_attachment=make_attachment(summarizer=rig.extraction),
                                        memory_extractor_factory=factory)
        self.session: str | None = None

    async def rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        return (await self.adapter.handle_client_request(request)).response

    async def open(self) -> None:
        reply = await self.rpc({"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(self.workspace), "mcpServers": []}})
        self.session = reply["result"]["sessionId"]
        await self.rpc({"jsonrpc": "2.0", "id": "mode", "method": "session/set_mode", "params": {"sessionId": self.session, "modeId": "chat"}})
        extractor = self.extractor
        if extractor is not None:  # the extractor's own outcome sink, teed: every skip, refusal and decision is recorded
            report = extractor._report
            extractor._report = lambda outcome: (self.rig.outcome(outcome), report(outcome))
        self.rig.model.project = self.project  # type: ignore[attr-defined]

    @property
    def state(self) -> Any:
        return self.adapter._sessions.get(self.session)

    @property
    def extractor(self) -> Any:
        return getattr(self.state, "memory_extractor", None)

    @property
    def project(self) -> str | None:
        extractor = self.extractor
        return None if extractor is None or getattr(extractor, "store", None) is None else extractor.store.project

    async def say(self, text: str, request_id: str) -> dict[str, Any]:
        return await self.rpc({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt",
                               "params": {"sessionId": self.session, "prompt": [{"type": "text", "text": text}]}})

    async def say_confirming(self, text: str, request_id: str, choice: str) -> dict[str, Any]:
        """A command that asks the user for a one-shot confirmation (purge, recovery location, restore), answered `choice`.
        A command refused before it asks (a rejected mapping) simply answers."""
        self.rig.asking = True
        try:
            task = asyncio.create_task(self.say(text, request_id))
            asked = asyncio.create_task(self.outbound.wait_for_request("session/request_permission"))
            done, _pending = await asyncio.wait({task, asked}, timeout=30, return_when=asyncio.FIRST_COMPLETED)
            if asked not in done:
                asked.cancel()
                return await asyncio.wait_for(task, timeout=60)
            request = asked.result()
            options = request["params"]["options"]
            picked = next(option["optionId"] for option in options if option["kind"].startswith(choice))
            self.outbound.respond(request["id"], {"outcome": {"outcome": "selected", "optionId": picked}})
            self.outbound.requests.clear()
            return await asyncio.wait_for(task, timeout=60)
        finally:
            self.rig.asking = False

    def settle(self, timeout: float = 20.0) -> None:
        """Wait for the session's extraction and checkpoint jobs, so what they append belongs to the input that caused it."""
        extractor = self.extractor
        deadline = time.monotonic() + timeout
        jobs = getattr(extractor, "_jobs", None)
        while jobs is not None and jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)  # the checkpoint for a settled turn is written after its answer


_WRITES = frozenset({"append", "restore", "purge", "checkpoint"})


class Rig:
    """One case's fresh world: its workspace repository and host config root, the stand-in models, the store, and the record
    of what happened."""

    def __init__(self, store: Store, base: Path, case_id: str) -> None:
        self.store = store
        self.root = base / case_id
        self.workspace = _new_repo(self.root / "ws")
        self.config = self.root / "config"
        self.config.mkdir()
        self.run = Run()
        self.model = _Model(self.run)
        self.extraction = _Extraction(self.run)
        self.host = Host(self, self.workspace, self.config)
        self.items: dict[str, str] = {}  # case key -> item id, as the run created them
        self.seen_stream: dict[str, str] = {}
        self.pending: dict[str, Any] = {}  # an operation an input arms for the next user input
        self.earlier: list[str] = []  # project ids of earlier registrations of this workspace (M21)
        self.exporter: dict[str, str] = {}  # recovery generation seal -> the project whose export wrote it
        self.asking = False  # the user's own command is asking for a confirmation now
        self.clock_seconds = 0.0  # how far the clock was moved on (`_op_clock`)
        self.appended: dict[tuple[str, str], tuple[str, int, str]] = {}  # (project, event id) -> (item, version, action) read
        self.committed: set[tuple[str, str]] = set()  # (project, event id) whose commit was observed

    # --- the host's store client: each request and its reply, then what it wrote ----------------------------------------

    def post(self, _settings: Any, *, timeout: float, path: str) -> Callable[[bytes], tuple[int, Any]]:
        def send(body: bytes) -> tuple[int, Any]:
            status, reply = self.store.service.handle(body, deadline=time.monotonic() + 5)
            with self.run.lock:
                self.exchanged(json.loads(body), status, reply)
            return status, reply

        return send

    def exchanged(self, request: Mapping[str, Any], status: int, reply: Any) -> None:
        """One request the host sent its store and the reply it got. Whatever the request wrote is read from the store's stream
        now, so it is placed right after the request; an append's commit counts only when this reply confirmed it durable, for
        this project's own event (F2), including a retry that confirms an event an earlier unconfirmed reply already wrote (the
        Gateway replays the same event: Codex CP4 review 3, finding 3)."""
        op, project = request.get("op"), request.get("project")
        if status != 200 or not isinstance(reply, dict) or not isinstance(project, str):
            return
        if op in _WRITES:
            self._stream(project)
        confirmed = (project, str(reply.get("event_id"))) if op == "append" and reply.get("durable_state") == "confirmed" else None
        if confirmed is not None and confirmed in self.appended and confirmed not in self.committed:
            self.committed.add(confirmed)
            item, version, action = self.appended[confirmed]
            self.run.add(f"commit.{action}", item, version, project)
        if op == "checkpoint" and reply.get("durable_state") == "confirmed":
            self.run.add("checkpoint", project=project)
        if op == "export" and reply.get("cursor") is None and reply.get("seal"):
            self.exporter[str(reply["seal"])] = project
        if op == "restore" and request.get("final") and reply.get("state") == "published":
            source = str(request.get("source", project))
            if source != project:
                self.run.mapped[project] = source
            wrote = self.exporter.get(str(request.get("generation")))
            if wrote is not None and wrote != project and source != wrote:
                self.run.add("restore.unmapped", project=project)

    def _stream(self, project: str) -> None:
        key = memory_store.MemoryStore._key(project, "events")
        for stream_id, fields in self.store.observer.xrange(key, min=f"({self.seen_stream.get(project, '0-0')}"):
            self.seen_stream[project] = stream_id.decode() if isinstance(stream_id, bytes) else stream_id
            event = json.loads(fields[b"e"]).get("event") or {}
            item, version, action, status = event.get("item"), event.get("version"), event.get("action"), event.get("status")
            if item is None:
                continue
            self.run.created_by.setdefault((project, item), self.run.seq)
            seen = self.run.history.setdefault((project, item), {})
            before = seen[max(seen)] if seen else None
            seen.setdefault(version, {name: event.get(name) for name in ("version", "action", "status", "trust", "kind")})
            if before is not None and before["trust"] != event.get("trust") and event.get("trust") != "off":
                self.run.add("store.trust_changed", item, version, project)
                if event.get("trust") == "user-authored":
                    self.run.add("store.trust_promoted", item, version, project)
            payload = self._payload(project, event)  # title, statement and lineage live in the payload hash, not the stream
            if action == "off":
                kind = ("store.off.archived" if status == "superseded" else "store.off.conflict" if status == "conflicted"
                        else "store.off.blocked" if payload.get("title") == memory_gate.BLOCKED_TITLE else "store.off")
                self.run.add(kind, item, version, project)
                continue
            self.run.add("store.off.conflict" if status == "conflicted" else f"store.{action}", item, version, project)
            if action == "admit" and event.get("trust") == "legacy-import":
                self.run.add("store.import", item, version, project)
            if self.pending.get("importing") and event.get("trust") not in ("legacy-import", "off"):
                self.run.add("store.trust_from_import", item, version, project)
            if action not in ("admit", "update"):
                continue
            statement = str(payload.get("statement", ""))
            if self._points_at_a_file(payload.get("lineage") or (), statement):
                self.run.add("store.pointer", item, version, project)
            if self._holds_a_file(statement):
                self.run.add("store.body", item, version, project)
            self.appended[(project, str(event.get("event_id")))] = (item, version, action)

    def _payload(self, project: str, event: Mapping[str, Any]) -> dict[str, Any]:
        """What the store holds for an event in its payload hash: title, statement, anchors and lineage ({} once purged)."""
        raw = self.store.observer.hget(memory_store.MemoryStore._key(project, "payloads"), str(event.get("event_id")))
        return dict(json.loads(raw)) if raw else {}

    def _holds_a_file(self, statement: str) -> bool:
        """Whether a saved statement holds the text of a file tracked in the workspace."""
        workspace = self.host.workspace
        for name in _git(workspace, "ls-files").splitlines():
            body = (workspace / name).read_text(encoding="utf-8", errors="replace").strip()
            if len(body) >= 8 and body in statement:
                return True
        return False

    def _points_at_a_file(self, lineage: Sequence[str], statement: str) -> bool:
        """Whether a saved item rests on a workspace file by reference (`file:` lineage) without holding that file's text."""
        for ref in lineage:
            if ref.startswith("file:"):
                path = self.host.workspace / ref[len("file:"):].rpartition("@")[0]
                body = path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else ""
                if not body or body not in statement:
                    return True
        return False

    # --- the host's ACP channel ---------------------------------------------------------------------------------------

    def card(self, host: Host | None, update: Mapping[str, Any]) -> None:
        item, version, durable = _citation(_card_text(update))
        head = str(update.get("title", "")).split(":")[0]
        kind = "card.unconfirmed" if durable == "unconfirmed" or head.startswith("Not saved yet") else f"card.{head}"
        self.run.add(kind, item, version, host.project if host else None)

    def card_failed(self, host: Host | None, update: Mapping[str, Any]) -> None:
        """A memory card the client never got: backlogged only if the project's durable backlog still holds that event."""
        item, version, _durable = _citation(_card_text(update))
        backlog = getattr(host.state, "memory_backlog", None) if host else None
        held = {record.get("event_id") for record in backlog.pending()} if backlog is not None else set()
        if str(update.get("toolCallId", ""))[len(CARD):] in held:
            self.run.add("card.backlogged", item, version, host.project if host else None)

    def answer(self, host: Host | None, text: str) -> None:
        """A command answer or reply the host sent, read in the order its parts say things happened."""
        project = host.project if host else None
        self.run.answers.append(text)
        if text.startswith("Not saved: the statement looks like it holds a secret"):
            self.run.add("answer.refused_secret", project=project)
        from optimus.acp import memory_commands as mc

        if text.startswith(mc.UNAVAILABLE[:40]) and self.run.command and len(self.model.requests) == self.run.requests_at_input:
            self.run.add("answer.unconfirmed", project=project)  # the host's reply to the command itself; no model wrote it
        if " cannot be switched on:" in text:
            self.run.add("answer.switch_on_unavailable", project=project)
        if "is retired." in text and text.startswith("Remembered"):
            self.run.add("answer.switched_on", project=project)
        if text.startswith("**Welcome back.**"):
            self.run.add("brief.request" if self.pending.pop("welcome_requested", False) else "brief.first", project=project)
        if "more than one earlier project claims this one" in text or "another workspace's registration" in text:
            self.run.add("restore.rejected", project=project)
        if "a deletion could be undone" in text or "a deletion is unfinished" in text:
            self.run.add("restore.held", project=project)
        if text.startswith("Restored "):  # the restore's own report, in the order it did things (Recovery.restore)
            steps: list[tuple[int, str, str | None, int | None]] = [(0, "restore.published", None, None)]
            if (at := text.find("is mapped to this one")) >= 0:
                steps.append((at, "restore.mapped", None, None))
            if (at := text.find("Pinned files hold for ")) >= 0:
                listed = text[at:text.find(".", at)]  # item ids and versions hold no dot: the sentence ends at the first
                steps += [(at, "restore.anchor", ref, int(version)) for ref, version in re.findall(r"`(m-[0-9a-f]{16})@([0-9]+)`", listed)]
            if (at := text.find("stay deleted")) >= 0:
                steps.append((at, "restore.tombstones", None, None))
            for _at, kind, item, version in sorted(steps, key=lambda step: step[0]):
                self.run.add(kind, item, version, project)

    # --- the host's own decisions ---------------------------------------------------------------------------------------

    def outcome(self, outcome: Any) -> None:
        self.run.outcomes.append({"seq": self.run.seq, "turn": outcome.turn_id, "purpose": outcome.purpose, "proposals": outcome.proposals,
                                  "skipped": outcome.skipped, "incomplete": outcome.incomplete, "refusals": list(outcome.refusals),
                                  "reasons": list(outcome.reasons)})

    def served_decision(self, commands: Any, served: Any) -> None:
        """The serving decision a turn's host made: what needs re-verification, and any live item it left out unexplained."""
        project = getattr(commands.store, "project", None)
        for item, version, _path in served.reverify:
            self.run.add("served.reverify", item, version, project)
        if served.omitted_optional or served.omitted_protected or not served.complete:  # who was left out cannot be told
            gap = "expiry: a serving decision left items out or was partial, so whether any live item expired is undecided"
            if gap not in self.run.uncovered:
                self.run.uncovered.append(gap)
            return
        from optimus_security.memory_store_contract import MAX_LIST

        accounted = {item.item for item in served.items} | {r[0] for r in served.reverify} | {e[0] for e in served.elsewhere}
        listed: set[str] = set()
        cursor = None
        while True:  # every page: a live item after a page of off records is still checked
            rows, cursor = commands.store.items("project", limit=MAX_LIST, cursor=cursor)
            for row in rows:
                listed.add(row.event.item)
                if row.event.status == "active" and row.event.trust != "off" and row.event.statement and row.event.item not in accounted:
                    self.run.add("served.expired", row.event.item, row.event.version, project)
            if not cursor:
                break
        for key in sorted(self.committed):  # an item whose commit was observed and that the listing no longer holds at all
            if key[0] == project and self.appended[key][0] not in listed:
                self.run.add("served.expired", self.appended[key][0], self.appended[key][1], project)

    def finish_input(self, host: Host | None = None) -> None:
        """What a case input left: its extraction and checkpoint jobs settled, the session's continuity, whether the host gave
        this session memory at all."""
        host = host or self.host
        host.settle()
        project = host.project
        if self.pending.pop("said", False) and getattr(host.state, "memory_commands", None) is None and host.extractor is None:
            self.run.add("answer.read_only")  # the host attached no memory to this session: its workspace could not be trusted
        continuity = getattr(host.state, "continuity", None)
        if continuity is None or self.pending.get(f"continuity:{host.session}"):
            return
        with contextlib.suppress(Exception):
            _stored, found = continuity.previous()
            if found is not None and found.checkpoint.session != host.session:
                self.pending[f"continuity:{host.session}"] = True
                self.run.add("brief.resumed", project=project)
                brief = continuity.brief()
                if "is not in this repository any more" in brief or "is not an ancestor of the current one" in brief:
                    self.run.add("brief.rewritten", project=project)


def _card_text(update: Mapping[str, Any]) -> str:
    return " ".join(part.get("content", {}).get("text", "") for part in update.get("content", []) if isinstance(part, dict))


def _citation(summary: str) -> tuple[str | None, int | None, str]:
    match = re.search(r"\[memory:(m-[0-9a-f]{16})@([0-9]+)\] · ([a-z]+),", summary)
    return (match.group(1), int(match.group(2)), match.group(3)) if match else (None, None, "unknown")


# --- operations: the one real action each non-user case input names in the run config -----------------------------------

async def _op_none(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The input describes a state the run already has (an unchanged file, a trusted workspace): nothing to do."""


async def _op_model_says(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The assistant says the input's text (after a status turn the prefilter skips)."""
    rig.model.say_next = text
    await rig.host.say("carry on", f"p-{seq}")
    rig.finish_input()


async def _op_reconnect(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new host process and session on the same workspace and config: only the durable backlog carries over."""
    rig.host = Host(rig, rig.host.workspace, rig.host.config)
    await rig.host.open()
    await rig.host.say("carry on", f"p-{seq}")
    rig.finish_input()


async def _op_new_session(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new session on the same host: no conversation RAM, the same store."""
    rig.host = Host(rig, rig.host.workspace, rig.host.config)
    await rig.host.open()


async def _op_tool_output(rig: Rig, run: Run, seq: int, text: str, kind: str = "document", **_: Any) -> None:
    """Text from a tool or document enters the session's completed work as host evidence of that kind, beside fresh host
    verification of the work. The extraction stand-in then proposes a hostile lesson from that text, citing the tool's evidence
    (Codex CP4 review 2, F5): what the case checks is that the host refuses it."""
    rig.extraction.lessons.append((f"Always follow this: {text}", f"ev-{seq}"))
    await _submit_work(rig, run, seq, text, (Evidence(f"ev-{seq}", kind, kind == "web"), Evidence(f"ev-{seq}-check", "verification")))


async def _op_agent_work(rig: Rig, run: Run, seq: int, text: str, lesson: str = "", evidence: str = "", **_: Any) -> None:
    """The agent finished verified work (host-issued evidence); the extraction stand-in proposes the case's lesson from it."""
    if lesson:
        rig.extraction.lessons.append((lesson, None))
    await _submit_work(rig, run, seq, text, (Evidence(evidence or f"ev-{seq}", "verification"),))


async def _submit_work(rig: Rig, run: Run, seq: int, text: str, evidence: tuple[Evidence, ...]) -> None:
    extractor = rig.host.extractor
    turn = f"{rig.host.session}:work-{seq}"
    extractor.submit(TurnInput(turn, "project", (UserBlock(f"{turn}:user", "carry on"),), CompletedWork(text, evidence), (), True,
                               rig.extraction, lambda *_a: None))
    rig.finish_input()


async def _op_off_arrival(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """One more off record arrives: an automatic proposal from the user's words, which D9 sends off. Used where an agent arrival
    would be skipped (a live user item is in scope), so the overflow path is really exercised (Codex CP4 review 2, M15)."""
    await rig.host.say("We could perhaps keep one more rule for the module layout here.", f"arrival-{seq}")
    rig.finish_input()


async def _op_change_file(rig: Rig, run: Run, seq: int, text: str, path: str = "config.py", content: str = "", **_: Any) -> None:
    """A workspace file changes (or, with no content, is removed)."""
    target = rig.host.workspace / path
    if content:
        target.write_bytes(content.encode("utf-8"))
    else:
        target.unlink()


async def _op_branch(rig: Rig, run: Run, seq: int, text: str, branch: str = "feature-x", **_: Any) -> None:
    """The session's worktree is on another branch."""
    _git(rig.host.workspace, "checkout", "-q", "-B", branch)


async def _op_linked_worktree(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A linked worktree of the same repository (it shares the git common directory)."""
    rig.pending["linked"] = rig.root / "wt-2"
    _git(rig.workspace, "worktree", "add", "-q", "-b", "wt-2", str(rig.pending["linked"]))


async def _op_move_to(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The session moves to the linked worktree: a new session there, on the same host config."""
    rig.host = Host(rig, rig.pending["linked"], rig.config)
    await rig.host.open()


async def _op_clone(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new session in a separate clone, with its own git common directory."""
    clone = rig.root / "clone"
    _git(rig.root, "clone", "-q", str(rig.workspace), str(clone))
    rig.host = Host(rig, clone, rig.config)
    await rig.host.open()


async def _op_untrusted(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The workspace cannot be registered as trusted: a directory whose git context is unavailable."""
    untrusted = rig.root / "untrusted"
    untrusted.mkdir()
    (untrusted / ".git").write_bytes(b"gitdir: ./missing-git-directory\n")
    rig.host = Host(rig, untrusted, rig.config)
    await rig.host.open()


async def _op_clock(rig: Rig, run: Run, seq: int, text: str, days: float = 0, **_: Any) -> None:
    """`days` pass: from now on the process clock (`time.time`, which the host, its continuity and the Gateway read) is that
    much later; run_case puts it back. Nothing is re-dated. Then a new session begins."""
    rig.clock_seconds += days * 24 * 3600
    time.time = lambda: _REAL_TIME() + rig.clock_seconds  # type: ignore[assignment]
    await _op_new_session(rig, run, seq, text)


async def _op_crash(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The host process dies during a turn. In process this run cannot kill the host mid-turn, so the crash is not exercised:
    it is recorded as missing coverage, owned by the live acpx kill proof (Codex CP4 review 2, F6)."""
    run.uncovered.append("crash: an interrupted, unsettled turn and real host process loss are not exercised in process "
                         "(owned by the Task 5 acpx kill proof)")


async def _op_restart(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A fresh host process: a new adapter and session on the same workspace and config."""
    await _op_new_session(rig, run, seq, text)


async def _op_rebase(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The branch is rewritten: the checkpoint's baseline commit no longer exists."""
    workspace = rig.host.workspace
    (workspace / "README.md").write_bytes(b"rewritten history\n")
    _git(workspace, "add", "README.md")
    _git(workspace, "commit", "-q", "--amend", "-m", "rewritten")
    _git(workspace, "reflog", "expire", "--expire=now", "--all")
    _git(workspace, "gc", "-q", "--prune=now")
    await _op_new_session(rig, run, seq, text)


async def _op_overflow(rig: Rig, run: Run, seq: int, text: str, count: int = 200, **_: Any) -> None:
    """`count` off records already exist for the project: made the only way one is made, by automatic proposals (D9)."""
    for n in range(count):
        await rig.host.say(f"We could perhaps keep rule number {n} for the module layout here.", f"fill-{seq}-{n}")
        rig.host.settle(5)
    rig.finish_input()


async def _op_compact(rig: Rig, run: Run, seq: int, text: str, turns: int = 3, **_: Any) -> None:
    """The context is compacted: status turns push the earlier ones past the attachment's tail, so the host's own compaction
    puts a summary in their place and hands their raw user text to extraction."""
    for n in range(turns):
        await rig.host.say("carry on", f"compact-{seq}-{n}")
        rig.finish_input()


async def _op_prior_off(rig: Rig, run: Run, seq: int, text: str, said: str = "I would probably go with tabs.", **_: Any) -> None:
    """An earlier session said `said` (D9 sent it off), then ended: its RAM-only source text went with it."""
    await rig.host.say(said, f"prior-{seq}")
    rig.finish_input()
    await _op_new_session(rig, run, seq, text)


async def _op_earlier_registration(rig: Rig, run: Run, seq: int, text: str, remember: Sequence[str] = (), purge: Sequence[int] = (),
                                   registrations: int = 1, lose_journal: bool = False, restore: bool = False, **_: Any) -> None:
    """Earlier registrations of this workspace (each a host config since lost, as on a machine set up again) saved `remember`,
    purged the items numbered in `purge`, and exported their recovery copy into the worktree. Then this host starts with a new
    config: a new project id for the same workspace. `lose_journal`: the Gateway's deletion journal is lost too. `restore`: the
    user then restores the first copy into this project with `/memory restore <generation> --map`, confirmed."""
    for registration in range(registrations):
        earlier = Host(rig, rig.workspace, rig.root / f"config-earlier-{seq}-{registration}")
        await earlier.open()
        for n, statement in enumerate(remember):
            await earlier.say(f"/remember {statement}", f"e-{seq}-{registration}-{n}")
            earlier.settle()
        rows, _cursor = earlier.extractor.store.items("project", limit=100)
        made = sorted(rows, key=lambda row: row.stream_id if hasattr(row, "stream_id") else row.event.valid_from_ms)
        for n in purge:
            event = made[n].event
            await earlier.say_confirming(f"/forget {event.item}@{event.version} --purge", f"e-purge-{seq}-{n}", "allow")
        await earlier.say_confirming("/memory export", f"e-export-{seq}-{registration}", "allow")
        rig.earlier.append(earlier.project or "")
    if lose_journal:
        rig.store.service = rig.store.gateway(rig.store.work / f"journal-lost-{seq}")
    await _op_new_machine(rig, run, seq, text)
    if restore:
        await rig.host.say_confirming(_resolve("/memory restore {gen} --map", rig), f"p-{seq}", "allow")
        rig.finish_input()


async def _op_new_machine(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new host config on the same workspace: the registry starts again, so the workspace gets a new project id."""
    rig.config = rig.root / f"config-{seq}"
    rig.config.mkdir()
    rig.host = Host(rig, rig.workspace, rig.config)
    await rig.host.open()


async def _op_delete_then_lose(rig: Rig, run: Run, seq: int, text: str, key: str = "pref-indent", purge: bool = False, **_: Any) -> None:
    """After the copy was taken, `key` is withdrawn (or purged) in this project; then the store's volume is really lost, and
    the user restores the same copy again, mapped, confirmed."""
    command = _resolve(f"/forget {{{key}@v}}" + (" --purge" if purge else ""), rig)
    if purge:
        await rig.host.say_confirming(command, f"p-{seq}-delete", "allow")
    else:
        await rig.host.say(command, f"p-{seq}-delete")
    rig.finish_input()
    rig.store.lose_volume()
    rig.appended.clear(), rig.committed.clear()  # the volume is really gone: what it held is not expected any more
    await _op_new_session(rig, run, seq, text)
    await rig.host.say_confirming(_resolve("/memory restore {gen} --map", rig), f"p-{seq}-again", "allow")
    rig.finish_input()


async def _op_import(rig: Rig, run: Run, seq: int, text: str, entries: Sequence[Mapping[str, str]] = (), mapped: str = "",
                     generation: bool = False, **_: Any) -> None:
    """The input's note store is imported (Plan 12.12 Task 2): an Agent Memory Repo whose `MEMORY.md` holds one bullet per note,
    `{project}` standing for this project's id; or, with `generation`, this project's newest recovery copy as it was exported.
    The user runs `/memory import <folder>`, then `/memory import apply <preview>`, and confirms."""
    from optimus.context import memory_recovery as mr

    if generation:
        state = rig.host.extractor.recovery.state()
        folder = Path(state.destination) / mr.generations(Path(state.destination))[0].name
    else:
        folder = rig.root / f"import-{seq}"
        folder.mkdir()
        lines = [f"- {e['statement']}" + (f" [{e['meta'].replace('{project}', rig.host.project or '')}]" if e.get("meta") else "")
                 for e in entries]
        (folder / "MEMORY.md").write_bytes(("# Notes\n\n" + "\n".join(lines) + "\n").encode("utf-8"))
    command = f"/memory import {folder}" + (f" --map {mapped}" if mapped else "")
    await rig.host.say(command, f"p-{seq}-preview")
    preview = re.search(r"imp-[0-9a-f]{12}", run.answers[-1] if run.answers else "")
    if preview is None:
        raise RuntimeError(f"no import preview: {(run.answers or [''])[-1][:200]}")
    rig.pending["importing"] = True
    try:
        await rig.host.say_confirming(f"/memory import apply {preview.group(0)}", f"p-{seq}", "allow")
    finally:
        rig.pending.pop("importing", None)
    rig.finish_input()


async def _op_linked_session(rig: Rig, run: Run, seq: int, text: str, branch: str = "feature-x", **_: Any) -> None:
    """A new session in a linked worktree of the same repository (it shares the git common directory), on `branch`."""
    linked = rig.root / "wt-2"
    _git(rig.workspace, "worktree", "add", "-q", "-b", branch, str(linked))
    rig.host = Host(rig, linked, rig.config)
    await rig.host.open()


OPS: Mapping[str, Callable[..., Any]] = {name[4:]: value for name, value in globals().items() if name.startswith("_op_")}


# --- trace ---------------------------------------------------------------------------------------------------------------

def to_trace(case: GoldenCase, run: Run, named: Mapping[str, str], items: Mapping[str, Any], *, source_id: str, config_id: str,
             reverify: Sequence[tuple[str, int]] = (), history: Mapping[str, Sequence[Mapping[str, Any]]] = {},
             project: str | None = None) -> ObservedTrace:
    """The grader's trace from what the run observed, for `project` (the case's project: the one whose final state is graded).
    `named` is case key -> the item the case input declared for that key created; `items` is the store's final state of every
    item in that project; `history` is each named item's versions as the store lists them now. An observation of another
    project's items is not this project's event. An item's versions are those the run saw being written, in this project or,
    under a published mapped restore, in the project mapped into it, then the store's own list; a version none of them shows is
    missing coverage, never reconstructed (Codex CP4 review 2, F7). An item no case key names is still an item: its own id
    keys it, so the grader's commit, notice and serving checks bind for it too."""
    key_of = {item: key for key, item in named.items()}

    def keyed(item: str | None) -> str | None:
        return None if item is None else key_of.get(item, item)

    events: list[TraceEvent] = []
    for observation in run.observations:
        name = EVENT_OF.get(observation.kind)
        if name is None or (project is not None and observation.project not in (None, project)):
            continue
        key = keyed(observation.item)
        events.append(TraceEvent(seq=len(events), type=name, memory_key=key, project_id=case.project_id if key else None,
                                 version=observation.version, rotation_id=None))
    stale = {item for item, _version in reverify}
    state = []
    unseen: list[str] = []
    for item, row in sorted(items.items()):
        known: dict[int, Mapping[str, Any]] = {entry["version"]: entry for entry in history.get(item, ())}
        source = run.mapped.get(project or "")
        if source is not None:
            known.update(run.history.get((source, item), {}))
        known.update(run.history.get((project or "", item), {}))
        known.setdefault(row.version, {"version": row.version, "action": row.action, "status": row.status, "trust": row.trust,
                                       "kind": row.kind})
        unseen += [f"history: {keyed(item)} v{n} was never observed" for n in range(1, max(known)) if n not in known]
        versions = [known[n] for n in sorted(known)]
        for entry, status in zip(versions, version_statuses(versions), strict=True):
            latest = entry["version"] == row.version
            state.append(MemoryStateObservation(
                key=keyed(item) or item, project_id=case.project_id, version=entry["version"], trust=_origin(entry["trust"], entry["kind"]),
                status=_status(entry["trust"], status, stale=latest and item in stale), off=entry["trust"] == "off",
                supersedes=entry["version"] - 1 if entry["action"] == "update" else None))
    served = [MemoryRef(memory_id=keyed(item) or item, version=version, project_id=case.project_id)
              for item, version in (run.served[-1] if run.served else [])]
    needed = (*case.required_events, *case.prohibited_events)
    missing = tuple(sorted({name for name in needed if name.split(":")[0] not in OBSERVABLE})) + tuple(unseen) + tuple(run.uncovered)
    return ObservedTrace(
        schema="plan12-memory-trace/1", case_id=case.case_id, case_version=case.version, source_id=source_id, config_id=config_id,
        events=tuple(events), evidence=(), served_memory=tuple(served), memory_state=tuple(state),
        answer=AnswerObservation(action="answer", claims=(), supported_by=(), support_extracted=False, citations=(), judge_status="uncertain"),
        attempts=(), provenance=(), reported_cost=ReportedCost(known_usd=Decimal("0"), complete=not missing, savings=None),
        coverage_complete=not missing, missing_coverage=missing, timing_ms=None)


def version_statuses(versions: Sequence[Mapping[str, Any]]) -> list[str]:
    """Each version's status in the grader's model; `versions` oldest first. The store appends a status change (a withdrawal,
    a purge, an overflow archive) as a new version and keeps each earlier version as written; the grader's versions are the
    item's contents. So a newer content version supersedes the live ones before it, a status change carries its status to
    them, and a purge purges every one before it."""
    statuses = [str(entry["status"]) for entry in versions]
    for index, entry in enumerate(versions):
        purge = entry["action"] == "tombstone"
        new = "purged" if purge else "superseded" if entry["action"] in ("admit", "update") else str(entry["status"])
        for earlier in range(index):
            if purge or (statuses[earlier] in _LIVE and new not in _LIVE):
                statuses[earlier] = new
    return statuses


def _origin(trust: str, kind: str) -> str:
    """An off record keeps no trust of its own: its kind says whose it was (a lesson, procedure or episode is the agent's)."""
    from context_engine.memory_contracts import AGENT_KINDS

    if trust != "off":
        return trust
    return "agent-derived" if kind in AGENT_KINDS else "user-authored"


def _status(trust: str, status: str, *, stale: bool) -> str:
    """The store's status, in the grader's words: an off record superseded by the overflow archive is archived; an active item
    whose pinned file changed needs re-verification (a serving-time condition, never stored)."""
    if trust == "off" and status == "superseded":
        return "archived"
    return "reverify" if stale and status == "active" else status


# --- one case ------------------------------------------------------------------------------------------------------------

def _resolve(text: str, rig: Rig) -> str:
    """`{key}` -> the item id the run created for that key; `{key@v}` -> id@its current version (what `/memory` shows)."""
    def one(match: re.Match[str]) -> str:
        key, versioned = match.group(1), match.group(2)
        item = rig.items.get(key, "m-0000000000000000")
        if not versioned:
            return item
        stored = rig.host.extractor.store.read(item) if rig.host.extractor is not None else None
        return f"{item}@{stored.event.version if stored is not None else 1}"

    def generation(match: re.Match[str]) -> str:
        from optimus.context import memory_recovery as mr

        earlier = rig.earlier[int(match.group(1) or 1) - 1]
        found = [g for g in mr.generations(mr.location(rig.workspace)) if g.project == earlier]
        return found[0].name if found else "gen-0-000000000000"

    text = re.sub(r"\{gen([0-9]?)\}", generation, text)
    return re.sub(r"\{([a-z0-9-]+)(@v)?\}", one, text)


async def drive(rig: Rig, case: GoldenCase, steps: Mapping[int, Sequence[Any]], keys: Mapping[int, Sequence[str]]) -> None:
    run = rig.run
    await rig.host.open()
    for item in case.inputs:
        step = list(steps.get(item.seq, ["say"] if item.actor == "user" else []))
        if not step:
            raise NotImplementedError(f"{case.case_id}: input {item.seq} ({item.actor}) names no operation in the run config")
        name, options = step[0], (step[1] if len(step) > 1 else {})
        run.seq = item.seq
        run.steps.append(f"{item.seq}:{item.actor}:{name}")
        if name in ("say", "confirm"):
            text = _resolve(options.get("text", item.text or ""), rig)
            rig.pending["said"] = True
            run.command, run.requests_at_input = text.lstrip().startswith("/"), len(rig.model.requests)
            rig.host.outbound.fail_cards = bool(options.get("cards_fail"))  # the client goes away after the commit
            try:
                if options.get("pause"):  # the store stalls (a paused container) while this input is saved
                    with rig.store.paused():
                        await rig.host.say(text, f"p-{item.seq}")
                elif name == "confirm":
                    await rig.host.say_confirming(text, f"p-{item.seq}", options.get("choice", "allow"))
                else:
                    if text.strip() == "/welcome":
                        rig.pending["welcome_requested"] = True
                    await rig.host.say(text, f"p-{item.seq}")
            finally:
                rig.host.outbound.fail_cards = False
            rig.finish_input()
        else:
            await OPS[name](rig, run, item.seq, item.text or "", **options)
        for seq, named in keys.items():
            created = [made for (_project, made), at in run.created_by.items() if at == seq]  # in the order the store appended them
            for key, made in zip(named, created, strict=False):
                rig.items.setdefault(key, made)


def final_items(rig: Rig) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """The store's final state of every item in the project (all pages), and each named item's versions, oldest first."""
    from optimus_security.memory_store_contract import MAX_HISTORY, MAX_LIST

    extractor = rig.host.extractor
    if extractor is None or getattr(extractor, "store", None) is None:
        return {}, {}
    found: dict[str, Any] = {}
    cursor = None
    while True:
        rows, cursor = extractor.store.items("project", limit=MAX_LIST, cursor=cursor)
        found.update({row.event.item: row.event for row in rows})
        if not cursor:
            break
    history = {}
    for item in set(rig.items.values()) & set(found):
        versions, more = extractor.store.history(item, limit=MAX_HISTORY)
        assert not more, f"{item} has more than {MAX_HISTORY} versions"
        history[item] = sorted(versions, key=lambda entry: entry["version"])
    return found, history


def _played(store: Store, base: Path, case: GoldenCase, entry: Mapping[str, Any], name: str) -> tuple[Rig, str | None, str | None, Any]:
    """One play of a case: its rig, any error and its cause, and the host's own serving function (for the final state)."""
    from optimus.acp import memory_commands as mc

    rig = Rig(store, base, name)
    rig.case = case  # type: ignore[attr-defined]
    keys = {int(seq): [key] if isinstance(key, str) else list(key) for seq, key in entry.get("keys", {}).items()}
    steps = {int(seq): step for seq, step in entry.get("steps", {}).items()}
    original = mc.MemoryCommands.served

    def served(commands: Any) -> Any:  # the decision each turn's host makes, recorded as it makes it
        result = original(commands)
        rig.served_decision(commands, result)
        return result

    error = cause = None
    mc.MemoryCommands.served = served  # type: ignore[method-assign]
    try:
        asyncio.run(drive(rig, case, steps, keys))
    except Exception as failure:  # noqa: BLE001 - a run that could not finish is reported with its cause, never graded PASS
        error, cause = f"{type(failure).__name__}: {failure}", traceback.format_exc()
    finally:
        mc.MemoryCommands.served = original  # type: ignore[method-assign]
        time.time = _REAL_TIME  # type: ignore[assignment]  # the clock an `_op_clock` moved
    return rig, error, cause, original


def run_case(store: Store, base: Path, case: GoldenCase, entry: Mapping[str, Any], *, source_id: str, config_id: str) -> dict[str, Any]:
    started = time.monotonic()
    rig, error, cause, serving = _played(store, base, case, entry, case.case_id)
    run = rig.run
    commands = getattr(rig.host.state, "memory_commands", None)
    reverify = []
    if error is None and commands is not None and getattr(commands, "store", None) is not None:
        reverify = [(item, version) for item, version, _path in serving(commands).reverify]
    items, history = final_items(rig) if error is None else ({}, {})
    project = rig.host.project or next((o.project for o in reversed(run.observations) if o.project), None)
    trace = to_trace(case, run, rig.items, items, source_id=source_id, config_id=config_id, reverify=reverify, history=history,
                     project=project)
    if error is not None:
        trace = unfinished(trace, error)
    verdict = grade_trace(case, trace)
    unrun = sorted({UNRUN_EVENTS[n.split(":")[0]] for n in case.required_events if n.split(":")[0] in UNRUN_EVENTS})
    result = {"case_id": case.case_id, "steps": run.steps, "error": error, "cause": cause, "seconds": round(time.monotonic() - started, 1),
              "unrun_owner": unrun, "clock_days": rig.clock_seconds / 86400,
              "qualification": qualification_view(case, verdict, unrun, trace),
              "outcomes": run.outcomes, "extraction_calls": run.calls,
              "trace": json.loads(trace.model_dump_json(by_alias=True)), "verdict": json.loads(verdict.model_dump_json())}
    mapped = MAPPED.get(case.case_id)
    if mapped is not None:
        result["mapped"] = {"error": error, **(mapped(rig, items) if error is None else {"status": "FAIL", "reasons": [error]})}
    check = EFFECTIVE.get(case.case_id)
    if check is not None:
        control = entry.get("control")
        if control is not None:  # the effective policy is exercised by its own play, never by the gold case's
            played = {**entry, "steps": {**entry.get("steps", {}), **control.get("steps", {})}}
            rig, error, cause, _serving = _played(store, base, case, played, f"{case.case_id}-control")
            items, _history = final_items(rig) if error is None else ({}, {})
        result["effective"] = {"control": control, "error": error, **check(rig, items)}
    return result


# --- what a zero-paid run decides ------------------------------------------------------------------------------------------

def unfinished(trace: ObservedTrace, error: str) -> ObservedTrace:
    """A run that could not finish: its cause is missing coverage, and it claims no complete cost (Codex CP4 review 3, finding 5)."""
    return trace.model_copy(update={"missing_coverage": (*trace.missing_coverage, f"run did not finish: {error}"), "coverage_complete": False,
                                    "reported_cost": trace.reported_cost.model_copy(update={"complete": False})})


PAID = "paid Zed sessions M3-ZED-OFF/ON/RETURN"
_EVIDENCE_REASON = re.compile(r"^requirement \S+ has no supporting evidence")


def qualification_view(case: GoldenCase, verdict: Any, unrun: Sequence[str], trace: ObservedTrace | None = None) -> dict[str, Any]:
    """What this zero-paid run decides (Codex CP4 gate 1, Q3; review 2, Q3); the grader's own verdict is kept beside it,
    unchanged. The authority and cost layers stand on what the host and store did. The answer layer is UNRUN: the stand-in model
    neither answers nor abstains on evidence; the paid Zed sessions own it. So is retrieval of evidence in a case that requires
    it (the stand-in runs no tools); any other retrieval failure (rank, scope) stays a FAIL. A case is never PASS here: at best
    INCONCLUSIVE, with any FAIL of a decided layer kept. A decay case (#235 M6) is UNRUN for its decay, but its own safety
    obligations stay decided here: no item expired, none was promoted or changed trust, every item expected active is."""
    layers = {name: layer.status for name, layer in verdict.layers.items()}
    owners = {"answer": PAID}
    layers["answer"] = "UNRUN"
    if case.required_evidence:
        owners["retrieval"] = PAID
        other = [reason for reason in verdict.layers["retrieval"].reasons if not _EVIDENCE_REASON.match(reason)]
        layers["retrieval"] = "FAIL" if verdict.layers["retrieval"].status == "FAIL" and other else "UNRUN"
    if unrun:
        safety = _safety(case, trace)
        return {"status": "FAIL" if safety["status"] == "FAIL" else "UNRUN", "layers": layers,
                "owners": {**owners, "case": ", ".join(unrun)}, "safety": safety}
    return {"status": "FAIL" if "FAIL" in layers.values() else "INCONCLUSIVE", "layers": layers, "owners": owners}


def _safety(case: GoldenCase, trace: ObservedTrace | None) -> dict[str, Any]:
    """The decay case's own safety checks. A failure the run observed is a FAIL whatever else is missing; only checks the run
    could not decide become INCONCLUSIVE (Codex CP4 review 3, finding 1)."""
    checked = [*SAFETY_EVENTS, "expected active items stay active"]
    if trace is None:
        return {"status": "INCONCLUSIVE", "reasons": ["the run produced no trace"], "checked": checked}
    reasons = [f"{event.type} at seq {event.seq}" for event in trace.events if event.type in SAFETY_EVENTS]
    # Only an item the run saw admitted (a confirmed commit, or a non-off version in the snapshot) can have expired: one never
    # admitted (captured off) did not. A finished run's snapshot is complete, so an admitted item missing from it is gone; a run
    # that did not finish has no snapshot, so that check is undecided (reviews 4 and 5).
    finished = not any(name.startswith("run did not finish:") for name in trace.missing_coverage)
    state = {(item.key, item.version): item for item in trace.memory_state}
    admitted = {event.memory_key for event in trace.events if event.type == "memory.committed" and event.memory_key}
    admitted |= {item.key for item in trace.memory_state if not item.off}
    undecided = []
    for expected in case.expected_memory:
        if expected.status != "active" or expected.key not in admitted:
            continue
        observed = state.get((expected.key, expected.version))
        if observed is None and not finished:
            undecided.append(f"{expected.key} v{expected.version}: no final snapshot")
        elif observed is None or observed.status != "active":
            reasons.append(f"{expected.key} v{expected.version} was admitted and is not active")
    if reasons:
        return {"status": "FAIL", "reasons": reasons, "checked": checked}
    gaps = [name for name in trace.missing_coverage if not name.startswith("memory.strength_")] + undecided
    if gaps:
        return {"status": "INCONCLUSIVE", "reasons": [f"undecided: {gap}" for gap in gaps], "checked": checked}
    return {"status": "PASS", "reasons": [], "checked": checked}


def _m09_skip(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    """M09 effective oracle (Codex CP4 review 2, Q4): with a live user item in scope the host skips agent extraction (the
    adopted scope-present skip), so no conflict record is paid for. Shown: the skip, no agent call, the user item unchanged and
    no agent admission."""
    run = rig.run
    skipped = [o for o in run.outcomes if o["purpose"] == AGENT_PURPOSE and o["skipped"] == "user_items_in_scope"]
    indent = items.get(rig.items.get("pref-indent", ""))
    reasons = ([] if skipped else ["no agent extraction was skipped for the user item in scope"]) + \
              (["an agent extraction call was made"] if "agent" in run.calls else []) + \
              ([] if indent is not None and (indent.version, indent.status, indent.trust) == (1, "active", "user-authored")
               else ["pref-indent is not v1 active user-authored"]) + \
              [f"agent item {item} was admitted" for item, row in items.items() if row.trust == "agent-derived"]
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "policy": "scope-present agent skip (Codex CP2 review 3)"}


def _m15_overflow(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    """M15 effective oracle (Codex CP4 review 2, Q4): at the off-record cap, one more off arrival moves the oldest live off
    record to the unserved archive; nothing is purged; the arrival stays an off record."""
    run = rig.run
    arrival = [made for (_project, made), at in run.created_by.items() if at == 2]
    archived = [o.item for o in run.observations if o.kind == "store.off.archived" and o.seq == 2]
    reasons = ([] if archived and not set(archived) & set(arrival) else ["no older off record was archived at the arrival"]) + \
              (["an item was purged"] if any(o.kind == "store.tombstone" for o in run.observations) else []) + \
              ([] if arrival and all(items.get(made) is not None and items[made].trust == "off" and items[made].status == "active"
                                     for made in arrival) else ["the arrival is not a live off record"])
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "archived": archived, "arrival": arrival,
            "policy": "oldest live off record archived at the cap (memory_store._archived)"}


def _m10_sanitized(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    """M10-a effective sanitation comparison (Codex CP4 review 2 ruling, review 5 ruling 2), on a control play whose second
    input tries to switch the off record on. The secret was redacted before extraction, so the outcome is an off record of the
    redacted words: shown here is that only permitted off metadata exists (no statement), that the secret is in nothing the
    store holds (its stream, every payload and checkpoint, decoded), that nothing was admitted, and that switch-on refused."""
    run = rig.run
    token = re.search(r"FAKE-TOKEN[A-Za-z0-9-]*", rig.case.inputs[0].text or "")  # type: ignore[attr-defined]
    project = rig.host.project or ""
    redis = rig.store.observer
    held = [value for value in redis.hgetall(memory_store.MemoryStore._key(project, "payloads")).values()]
    held += [fields[b"e"] for _id, fields in redis.xrange(memory_store.MemoryStore._key(project, "events"))]
    text = b"\n".join(held).decode("utf-8", "replace")
    offs = [row for row in items.values() if row.trust == "off"]
    reasons = ([] if token else ["the case input names no token"]) + \
              ([f"{token.group(0)} is in what the store holds"] if token and token.group(0) in text else []) + \
              (["an item was admitted"] if any(o.kind.startswith("commit.") for o in run.observations) else []) + \
              ([] if offs and all(not row.statement for row in offs) else ["no off record, or one that keeps a statement"]) + \
              ([] if any(" cannot be switched on:" in answer or answer.startswith("Not saved") for answer in run.answers)
               else ["switch-on was not refused"])
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "searched_bytes": len(text),
            "policy": "redaction before extraction, then automatic off capture with metadata only"}


def _import_status(rig: Rig) -> str:
    commands = getattr(rig.host.state, "memory_commands", None)
    importer = getattr(commands, "_importer", None)
    return importer.status() if importer is not None else ""


def _served_items(rig: Rig) -> set[str]:
    return {o.item for o in rig.run.observations if o.kind == "served" and o.item}


def _mapped_only(rig: Rig, items: Mapping[str, Any], key: str, statement: str, refused: int) -> list[str]:
    """Only the mapped note (its exact words, as the run config gives them) is stored, as legacy-import optional; nothing else
    of the import is stored; the import's own status counts exactly `refused` refused notes."""
    kept = rig.items.get(key)
    row = items.get(kept or "")
    others = [i for i, r in items.items() if i != kept and r.trust == "legacy-import"]
    found = re.search(r"(\d+) refused", _import_status(rig))
    return (([] if row is not None and (row.trust, row.status, row.kind, row.statement) == ("legacy-import", "active", "fact", statement)
             else [f"{key} is not stored as active legacy-import with its words"]) +
            [f"another imported item {i} is stored" for i in others] +
            ([f"{i} became user-authored" for i, r in items.items() if r.trust == "user-authored"]) +
            ([] if found is not None and int(found.group(1)) == refused else [f"import status does not report exactly {refused} refused"]) +
            [f"an observed {o.kind}" for o in rig.run.observations if o.kind in ("store.trust_from_import", "store.trust_promoted")])


def _m13a(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    reasons = _mapped_only(rig, items, "n-alpha-1", "The CI uses uv.", 2)
    served = _served_items(rig)
    reasons += [f"served {i}, not the mapped note" for i in served if i != rig.items.get("n-alpha-1")]
    reasons += [] if rig.items.get("n-alpha-1") in served else ["the mapped note was not served at the question"]
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons,
            "invariant": "only the mapped proj-alpha note is stored and served, as optional context"}


def _m13b(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    reasons = _mapped_only(rig, items, "n-alpha-2", "Always use tabs.", 0)
    row = items.get(rig.items.get("n-alpha-2", ""))
    if row is not None and "claimed-origin:user" not in (row.lineage or ()):
        reasons.append("the user-authored claim is not kept as an inert claimed origin")
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "invariant": "stored as legacy-import active optional; "
            "never user-authored", "unrun": ["the answer abstains from asserting a user rule: " + PAID]}


def _m13c(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    run = rig.run
    keys = ("n-alpha-4", "lesson-squash")
    reasons = [f"{key} was never created" for key in keys if key not in rig.items]
    from optimus.context import memory_recovery as mr

    exported: dict[str, Any] = {}
    state = rig.host.extractor.recovery.state() if rig.host.extractor is not None else None
    if state is not None and state.destination:
        newest = mr.generations(Path(state.destination))
        if newest:  # the copy the user exported at seq 4 (nothing changed after it: the re-import stored nothing)
            _manifest, entries = mr.read_generation(Path(state.destination) / newest[0].name, rig.host.project)
            exported = {shaped["entry"]["item"]: shaped["entry"] for shaped in entries}
    for key, origin in zip(keys, ("legacy-import", "agent-derived"), strict=True):
        row = items.get(rig.items.get(key, ""))
        if row is None:
            reasons.append(f"{key} is not in the store")
        elif (row.trust, row.status, row.statement) != (origin, "withdrawn", ""):
            reasons.append(f"{key} is {row.trust} {row.status}, not withdrawn {origin} without payload")
        entry = exported.get(rig.items.get(key, ""))
        if entry is None or (entry.get("trust"), entry.get("status"), entry.get("statement", "")) != (origin, "withdrawn", ""):
            reasons.append(f"{key}'s exported entry is not its payload-free {origin} lifecycle")
    reasons += [f"{key} served" for key in keys if rig.items.get(key) in _served_items(rig)]
    reasons += [f"an observed {o.kind}" for o in run.observations
                if o.kind in ("store.trust_from_import", "store.trust_promoted", "store.trust_changed")]
    reasons += [f"the re-import stored {o.item}" for o in run.observations if o.kind.startswith("store.") and o.seq == 5]
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "invariant": "neither item is served before or after "
            "re-import; neither gains user trust or is promoted; origins survive; no statement is recovered",
            "coverage_note": "re-import into a project already holding the items proves no reactivation or promotion only; the "
                             "re-import reads the copy's MEMORY.md, which lists no inactive item, so it never reads the payload-free "
                             "lifecycle entries (entries.jsonl is not Markdown): their origins are checked in the exported copy"}


def _m18c(rig: Rig, items: Mapping[str, Any]) -> dict[str, Any]:
    reasons = _mapped_only(rig, items, "n-alpha-3", "Run the tests with pytest -q.", 2)
    served = _served_items(rig)
    reasons += [] if rig.items.get("n-alpha-3") in served else ["the mapped note was not served in the linked worktree"]
    reasons += [f"served {i}, not the mapped note" for i in served if i != rig.items.get("n-alpha-3")]
    linked = rig.host.workspace.name == "wt-2" and rig.host.project == next(
        (o.project for o in rig.run.observations if o.kind == "store.import"), None)
    reasons += [] if linked else ["the question did not run in a linked worktree of the importing registration"]
    return {"status": "FAIL" if reasons else "PASS", "reasons": reasons, "invariant": "only the mapped proj-alpha note is "
            "served in the linked worktree; the others are never stored with a statement or served; dispositions recorded",
            "coverage_note": "the original's storage-state mismatch (n-unknown-3 stored off versus absent) is reported beside "
                             "this result"}


# Plan 12.12 Task 2: each case's mapped comparison under the agreed translation table (decisions.json oracle_mapping). A mapped
# PASS proves only its named invariant; the original comparison is kept beside it, unchanged.
MAPPED: Mapping[str, Callable[[Rig, Mapping[str, Any]], dict[str, Any]]] = {"M13-a": _m13a, "M13-b": _m13b, "M13-c": _m13c,
                                                                           "M18-c": _m18c}


EFFECTIVE: Mapping[str, Callable[[Rig, Mapping[str, Any]], dict[str, Any]]] = {
    "M09-a-D10": _m09_skip, "M15-a-D10": _m15_overflow, "M10-a": _m10_sanitized}


# --- inputs ----------------------------------------------------------------------------------------------------------------

def load_cases(path: Path) -> dict[str, GoldenCase]:
    """A fixture's cases. A variant fixture (one with a `decision`) is checked first (Codex CP4 gate 1, Q2; review 2, F10): the
    decision file it names has the digest it pins, and every variant's gold equals its original's in the `base` fixture."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if "decision" in document:
        check_variants(document)
    return {raw["case_id"]: GoldenCase.model_validate(raw) for raw in document["cases"]}


def check_variants(document: Mapping[str, Any]) -> None:
    decision = document["decision"]
    digest = "hex:" + hashlib.sha256(Path(decision["path"]).read_bytes()).hexdigest()
    if digest != decision["sha256"]:
        raise ValueError(f"{decision['path']} does not have the digest the variant fixture pins")
    originals = {raw["case_id"]: raw for raw in json.loads(Path(document["base"]).read_text(encoding="utf-8"))["cases"]}
    for variant in document["cases"]:
        original = originals.get(str(variant["case_id"]).removesuffix("-D10"))
        if not str(variant["case_id"]).endswith("-D10") or original is None:
            raise ValueError(f"{variant['case_id']} is not a -D10 variant of a case in {document['base']}")
        if _gold(variant) != _gold(original):
            raise ValueError(f"{variant['case_id']} changes its original's gold")


def _gold(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Everything a variant must keep: all but its id, its provenance and the words of its user inputs."""
    kept = {name: value for name, value in raw.items() if name not in ("case_id", "provenance", "inputs")}
    kept["inputs"] = [{name: value for name, value in item.items() if not (name == "text" and item.get("actor") == "user")}
                      for item in raw["inputs"]]
    return kept


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", default="", help="comma-separated case ids; default: every case in the run config")
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(encoding="utf-8"))
    from tests.integration.memory.conftest import RELEASE_FLAG

    if not os.environ.get(RELEASE_FLAG):
        raise SystemExit(f"UNRUN: {RELEASE_FLAG} is not set; the released test store is required")
    cases: dict[str, GoldenCase] = {}
    for fixture in config["fixtures"]:
        cases.update(load_cases(Path(fixture)))
    chosen = [c for c in args.cases.split(",") if c] or list(config["cases"])
    source = "git:" + subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "src", "tools", "tests"], capture_output=True, text=True).stdout.strip())
    work = Path(tempfile.mkdtemp(prefix="m3q-"))
    results = []
    try:
        store = Store(work)
        for case_id in chosen:
            result = run_case(store, work / "cases", cases[case_id], config["cases"].get(case_id, {}), source_id=source,
                              config_id=config["config_id"])
            results.append(result)
            print(case_id, result["qualification"]["status"], result["qualification"]["layers"],
                  (result.get("effective") or {}).get("status", ""), (result.get("mapped") or {}).get("status", ""),
                  result["error"] or "", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    args.output.mkdir(parents=True, exist_ok=True)
    document = {"schema": SCHEMA, "source": source, "dirty": dirty, "config_id": config["config_id"], "results": results}
    (args.output / "results.json").write_bytes((json.dumps(document, indent=1, ensure_ascii=True) + "\n").encode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
