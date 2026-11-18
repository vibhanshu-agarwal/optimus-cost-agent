"""Plan 12.11 Task 5 qualification: `python -m tools.plan12_memory.m3_evaluate --config reports/plan12-memory-m3/run-config.json
--output tmp/plan12-memory-m3`.

Each case is driven through the production host: the real ACP adapter, the host memory commands, the launch's own extractor
factory and the Gateway's memory handler on the released test store (`p1211-cp4-test-redis`). Its trace is built only from what
that run observably did, never from the case's expectations:

- the store's own event stream: every append, with its action, trust, status and version, and each item's version history;
- the Gateway's commit result for each append, as the host received it (durably confirmed or not);
- the host's memory cards on the ACP channel (`memory/<event_id>`): the headline and citation;
- the memory block each model turn was served, and the items left out with their reason;
- checkpoints, the welcome brief, command answers and recovery replies, read from the host's own output.

One fixed table (`EVENT_OF`) turns those observations into the grader's event names. A needed name the run cannot observe goes
into `missing_coverage`, so the case cannot pass. The models are local stand-ins with zero paid calls: answer quality and
extraction quality stay with the released paid Zed sessions, so the answer layer is INCONCLUSIVE here by the grader's own rule.

Case inputs are natural-language scenarios. A user input is said as written. Every other input names, in the run config, the one
real operation that carries it out (`OPS`): a paused store, a dropped card, a changed file, a killed host, a git rebase, a clock
shift, the agent's completed work, a lost store volume. Case keys (`pref-indent`) name the item a given case input created, as
the run config declares; a `{key}` or `{key@v}` in a command is the id (and current version) the user would read in `/memory`.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import traceback
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydantic import SecretStr

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.agent.models import AgentRunResult, AgentRunStatus
from optimus.context.maintenance import SummarizerAttempt, SummarizerResponse
from optimus.context.memory_extraction import CompletedWork, Evidence, TurnInput, UserBlock, extractor_factory
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
# The fixed translation from an observation to the grader's event name. An observation of an item carries that item's case key.
EVENT_OF: Mapping[str, str] = {
    "commit.admit": "memory.committed",  # an append the store's commit result confirmed durable
    "commit.update": "memory.committed",
    "store.update": "memory.superseded",
    "store.withdraw": "memory.withdrawn",
    "store.tombstone": "memory.purged",
    "store.off": "memory.candidate.off",
    "store.off.archived": "memory.archived_overflow",
    "store.off.conflict": "memory.conflict.off",
    "store.off.blocked": "memory.secret_refused",
    "card.Remembered": "memory.notice.remembered",
    "card.Updated": "memory.notice.remembered",
    "notice.unconfirmed": "memory.notice.unconfirmed",
    "notice.backlogged": "memory.notice.backlogged",
    "answer.refused_secret": "memory.secret_refused",  # pragma: allowlist secret
    "answer.read_only": "memory.blocked_untrusted_workspace",
    "answer.switched_on": "memory.switched_on",
    "answer.switch_on_unavailable": "memory.switch_on_unavailable",
    "served": "memory.served",
    "served.reverify": "memory.reverify",
    "checkpoint": "checkpoint.written",
    "brief.first": "brief.shown.first_response",
    "brief.request": "brief.shown.on_request",
    "brief.resumed": "continuation.resumed",
    "brief.rewritten": "continuation.baseline_rewritten",
    "restore.published": "restore.published",
    "restore.mapped": "restore.rekey_mapped",
    "restore.tombstones": "restore.tombstones_applied",
    "restore.anchor": "restore.anchor_mapped",
    "restore.rejected": "restore.mapping_rejected",
    "restore.held": "restore.held_unserved",
    "prompt.from_summary": "memory.extracted_from_summary",
    "store.pointer": "memory.pointer_only",
    "store.body": "memory.body_persisted",  # a saved statement holds a workspace file's text
}
# Names this harness can observe: when one is absent, the run observed its absence. Any other needed name is missing coverage.
OBSERVABLE = frozenset(EVENT_OF.values()) | {"memory.trust_promoted", "memory.trust_changed", "memory.expired", "memory.prompt_user",
                                              "restore.rekey_unmapped"}
# Never observable here, with the owner of the evidence (plan v5 Evaluation): reported UNRUN, never PASS.
UNRUN_EVENTS = {"memory.strength_faded": "#235 M6 (decay)", "memory.strength_raised": "#235 M6 (decay)"}


@dataclass
class Observation:
    seq: int
    kind: str  # an EVENT_OF key
    item: str | None = None
    version: int | None = None


@dataclass
class Run:
    """What one case's run observed, in order."""

    observations: list[Observation] = field(default_factory=list)
    served: list[list[tuple[str, int]]] = field(default_factory=list)  # per model turn: (item, version) served
    created_by: dict[str, int] = field(default_factory=dict)  # item -> the case input whose turn first appended it
    answers: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)  # what each input did, for the report

    def add(self, kind: str, item: str | None = None, version: int | None = None) -> None:
        self.observations.append(Observation(len(self.observations), kind, item, version))


class _Keyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, name: str) -> str | None:
        return self.values.get((service, name))

    def set_password(self, service: str, name: str, value: str) -> None:
        self.values[(service, name)] = value

    def delete_password(self, service: str, name: str) -> None:
        self.values.pop((service, name), None)


class _Model:
    """The zero-paid stand-in for the session's model: a Chat answer that states no fact, so the answer layer cannot pass here.
    `say_next` makes the next answer a given text (an assistant input of a case)."""

    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.say_next: str | None = None

    def run(self, request: Any, **_kwargs: Any) -> AgentRunResult:
        self.requests.append(request)
        text, self.say_next = self.say_next or "(controlled stand-in answer)", None
        common = dict(run_id=request.run_id, session_id=request.session_id, tool_calls=(), mutation_count=0, provider_keys_resolvable=())
        return AgentRunResult(execution_mode=ExecutionMode.CHAT, status=AgentRunStatus.COMPLETED, final_state="CHAT_ONLY",
                              output_text=text, total_cost_usd=Decimal("0"), **common)


class _Extraction:
    """The zero-paid stand-in for the summarizer route. For user extraction it proposes each block whole, as a question when it
    asks one and as a preference otherwise; D9 sends every automatic user proposal off, so its wording never becomes memory. For
    agent extraction it proposes the lessons the case's completed work queued. Context summaries get a fixed valid summary."""

    def __init__(self) -> None:
        self.calls = 0
        self.lessons: list[str] = []
        self.prompts: list[str] = []

    def __call__(self, *, prompt: str, max_output_tokens: int, purpose: str = "") -> SummarizerResponse:
        self.calls += 1
        self.prompts.append(prompt)
        attempt = SummarizerAttempt(f"stand-in-{self.calls}", f"gw-stand-in-{self.calls}", "completed", Decimal("0"))
        if prompt.startswith("You extract at most a few optional lessons"):
            refs = re.findall(r"^- (\S+) \(", prompt, re.M)
            candidates = [{"speech_act": "assertion", "kind": "lesson", "title": text[:60], "statement": text, "evidence": refs[:1]}
                          for text in self.lessons]
            self.lessons = []
        elif prompt.startswith("You extract"):
            candidates = []
            for block, text in re.findall(r'<block id="([^"]+)">(.*?)</block>', prompt, re.S):
                act = "question" if text.rstrip().endswith("?") else "preference"
                candidates.append({"speech_act": act, "kind": "preference", "title": text[:60], "statement": text,
                                   "spans": [{"block": block, "start": 0, "end": len(text)}]})
        else:
            from tests.unit.acp.test_context_engine_admission import SUMMARY

            return SummarizerResponse(text=SUMMARY, finish_status="stop", attempts=(attempt,))
        return SummarizerResponse(text=json.dumps({"candidates": candidates}), finish_status="stop", attempts=(attempt,))


class _CardsFail(RecordingOutboundChannel):
    """A client connection whose memory cards cannot be sent: the client went away after the commit."""

    async def notify(self, method: str, params: dict[str, Any], **kwargs: Any) -> Any:
        if params.get("update", {}).get("sessionUpdate") == "tool_call":
            raise ConnectionError("the client went away")
        return await super().notify(method, params, **kwargs)


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

    def __init__(self, rig: Rig, workspace: Path, config: Path, *, outbound: RecordingOutboundChannel | None = None) -> None:
        self.rig, self.workspace, self.config = rig, workspace, config
        self.outbound = outbound or RecordingOutboundChannel()
        settings = SimpleNamespace(optimus_api_key=SecretStr("m3-qualification"))
        factory = extractor_factory(config_root=config, settings=settings, post=rig.post)
        from tests.unit.acp.test_context_engine_admission import make_attachment

        self.adapter = AcpDuplexAdapter(runner=rig.model, workspace_root=workspace, sessions=InMemoryAcpSpecSessionStore(),
                                        outbound=self.outbound, context_attachment=make_attachment(summarizer=rig.extraction),
                                        memory_extractor_factory=factory)
        self.session: str | None = None
        self.seen_updates = 0

    async def rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        return (await self.adapter.handle_client_request(request)).response

    async def open(self) -> None:
        reply = await self.rpc({"jsonrpc": "2.0", "id": "new", "method": "session/new", "params": {"cwd": str(self.workspace), "mcpServers": []}})
        self.session = reply["result"]["sessionId"]
        await self.rpc({"jsonrpc": "2.0", "id": "mode", "method": "session/set_mode", "params": {"sessionId": self.session, "modeId": "chat"}})

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
        task = asyncio.create_task(self.rpc({"jsonrpc": "2.0", "id": request_id, "method": "session/prompt",
                                             "params": {"sessionId": self.session, "prompt": [{"type": "text", "text": text}]}}))
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

    def settle(self, timeout: float = 20.0) -> None:
        """Wait for the session's extraction and checkpoint jobs, so what they append is observed with the turn that caused it."""
        extractor = self.extractor
        deadline = time.monotonic() + timeout
        jobs = getattr(extractor, "_jobs", None)
        while jobs is not None and jobs.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)  # the checkpoint for a settled turn is written after its answer


class Rig:
    """One case's fresh world: its workspace repository and host config root, the stand-in models, and the store."""

    def __init__(self, store: Store, base: Path, case_id: str) -> None:
        self.store = store
        self.root = base / case_id
        self.workspace = _new_repo(self.root / "ws")
        self.config = self.root / "config"
        self.config.mkdir()
        self.model = _Model()
        self.extraction = _Extraction()
        self.host = Host(self, self.workspace, self.config)
        self.items: dict[str, str] = {}  # case key -> item id, as the run created them
        self.seen_stream: dict[str, str] = {}
        self.checkpoints: dict[str, int] = {}
        self.pending: dict[str, Any] = {}  # an operation an input arms for the next user input
        self.earlier: list[str] = []  # project ids of earlier registrations of this workspace (M21)
        self.confirmed: set[tuple[str, int]] = set()  # (item, version) appends whose commit result the Gateway gave as durable

    def post(self, _settings: Any, *, timeout: float, path: str) -> Callable[[bytes], tuple[int, Any]]:
        def send(body: bytes) -> tuple[int, Any]:
            status, reply = self.store.service.handle(body, deadline=time.monotonic() + 5)
            if isinstance(reply, dict) and reply.get("durable_state") == "confirmed" and "item" in reply:
                self.confirmed.add((reply["item"], reply["version"]))
            return status, reply

        return send

    def observe(self, run: Run, seq: int, host: Host | None = None) -> None:
        """Everything this case input caused, in causal order: the store's appends, then the host's output and served blocks."""
        host = host or self.host
        host.settle()
        project = host.project
        updates = [n["params"]["update"] for n in host.outbound.notifications if n["method"] == "session/update"]
        new_updates = updates[host.seen_updates:]
        host.seen_updates = len(updates)
        if project is not None:
            self._stream(run, seq, project)
            self._checkpoints(run, project, host)
        elif self.pending.pop("said", False) and getattr(host.state, "memory_commands", None) is None:
            run.add("answer.read_only")  # the host attached no memory to this session: its workspace could not be trusted
        for update in new_updates:
            if update.get("sessionUpdate") == "tool_call" and str(update.get("toolCallId", "")).startswith(CARD):
                title = str(update.get("title", ""))
                item, version, durable = _citation(_card_text(update))
                head = title.split(":")[0]
                run.add("notice.unconfirmed" if durable == "unconfirmed" or head.startswith("Not saved yet") else f"card.{head}", item, version)
            elif update.get("sessionUpdate") == "agent_message_chunk":
                text = update.get("content", {}).get("text", "")
                run.answers.append(text)
                self._answer(run, text)
        for request in self.model.requests[len(run.served):]:
            served = [(ref.split("@")[0], int(ref.split("@")[1])) for ref in re.findall(r"^- \[memory:(m-[0-9a-f]{16}@[0-9]+)\]",
                                                                                         request.memory_context or "", re.M)]
            run.served.append(served)
            for item, version in served:
                run.add("served", item, version)
            for item in _reverify(host, request):
                run.add("served.reverify", item[0], item[1])
        for prompt in self.extraction.prompts:
            if "<summary" in prompt or "Summary of earlier" in prompt:
                run.add("prompt.from_summary")
        self.extraction.prompts.clear()
        self._continuity(run, host)
        if self.pending.pop("restored_now", False) and host.extractor is not None:
            from optimus.context import memory_serving

            for item, made in run.created_by.items():
                stored = host.extractor.store.read(item) if made == seq else None
                lineage = stored.event.lineage if stored is not None else ()
                if any(ref.startswith("file:") for ref in lineage) and memory_serving.changed_file(lineage, host.workspace) is None:
                    run.add("restore.anchor", item, stored.event.version)  # its pinned file holds in this workspace

    def _continuity(self, run: Run, host: Host) -> None:
        """What the host's continuity resolved for this session: an earlier session's checkpoint it continues from, and whether
        that checkpoint's baseline commit is gone (the brief would say so)."""
        continuity = getattr(host.state, "continuity", None)
        if continuity is None or self.pending.get(f"continuity:{host.session}"):
            return
        with contextlib.suppress(Exception):
            _stored, found = continuity.previous()
            if found is not None and found.checkpoint.session != host.session:
                self.pending[f"continuity:{host.session}"] = True
                run.add("brief.resumed")
                brief = continuity.brief()
                if "is not in this repository any more" in brief or "is not an ancestor of the current one" in brief:
                    run.add("brief.rewritten")

    def _stream(self, run: Run, seq: int, project: str) -> None:
        key = memory_store.MemoryStore._key(project, "events")
        for stream_id, fields in self.store.observer.xrange(key, min=f"({self.seen_stream.get(project, '0-0')}"):
            self.seen_stream[project] = stream_id.decode() if isinstance(stream_id, bytes) else stream_id
            event = json.loads(fields[b"e"]).get("event") or {}
            item, version, action = event.get("item"), event.get("version"), event.get("action")
            if item is None:
                continue
            run.created_by.setdefault(item, seq)
            if action == "off":
                status, title = event.get("status"), event.get("title", "")
                kind = "store.off.archived" if status == "superseded" else "store.off.blocked" if title.startswith("(blocked") else "store.off"
                run.add(kind, item, version)
                continue
            run.add(f"store.{action}", item, version)
            if action not in ("admit", "update"):
                continue
            stored = self.host.extractor.store.read(item)
            if stored is not None and self._points_at_a_file(stored):
                run.add("store.pointer", item, version)
            if stored is not None and self._holds_a_file(stored):
                run.add("store.body", item, version)
            if (item, version) in self.confirmed:
                run.add(f"commit.{action}", item, version)  # the Gateway's commit result, as the host received it

    def _holds_a_file(self, stored: Any) -> bool:
        """Whether a saved statement holds the text of a file tracked in the workspace."""
        workspace = self.host.workspace
        for name in _git(workspace, "ls-files").splitlines():
            body = (workspace / name).read_text(encoding="utf-8", errors="replace").strip()
            if len(body) >= 8 and body in stored.event.statement:
                return True
        return False

    def _points_at_a_file(self, stored: Any) -> bool:
        """Whether a saved item rests on a workspace file by reference (`file:` lineage) without holding that file's text."""
        for ref in stored.event.lineage:
            if ref.startswith("file:"):
                path = self.host.workspace / ref[len("file:"):].rpartition("@")[0]
                body = path.read_text(encoding="utf-8", errors="replace").strip() if path.is_file() else ""
                if not body or body not in stored.event.statement:
                    return True
        return False

    def _checkpoints(self, run: Run, project: str, host: Host) -> None:
        from optimus_security.memory_store_contract import MAX_CHECKPOINTS

        for stored in host.extractor.store.checkpoints(limit=MAX_CHECKPOINTS):  # the newest; this harness writes far fewer per step
            identity = f"{project}/{stored.checkpoint.session}/{stored.checkpoint.sequence}"
            if identity not in self.checkpoints:
                self.checkpoints[identity] = 1
                run.add("checkpoint")

    def _answer(self, run: Run, text: str) -> None:
        from optimus.acp import memory_commands as mc

        if text.startswith("Not saved: the statement looks like it holds a secret"):
            run.add("answer.refused_secret")
        if text.startswith(mc.READ_ONLY[:40]):
            run.add("answer.read_only")
        if text.startswith(mc.UNAVAILABLE[:40]):
            run.add("notice.unconfirmed")
        if " cannot be switched on:" in text:
            run.add("answer.switch_on_unavailable")
        if "is retired." in text and text.startswith("Remembered"):
            run.add("answer.switched_on")
        if text.startswith("**Welcome back.**"):
            run.add("brief.request" if self.pending.pop("welcome_requested", False) else "brief.first")
        if text.startswith("Restored "):
            run.add("restore.published")
            self.pending["restored_now"] = True
            if "is mapped to this one" in text:
                run.add("restore.mapped")
            if "were deleted since and stay deleted" in text:
                run.add("restore.tombstones")
        if "more than one earlier project claims this one" in text or "another workspace's registration" in text:
            run.add("restore.rejected")
        if "a deletion could be undone" in text or "a deletion is unfinished" in text:
            run.add("restore.held")


def _reverify(host: Host, request: Any) -> list[tuple[str, int]]:
    commands = getattr(host.state, "memory_commands", None)
    if commands is None or getattr(commands, "store", None) is None:
        return []
    with contextlib.suppress(Exception):
        return [(item, version) for item, version, _path in commands.served().reverify]
    return []


def _card_text(update: Mapping[str, Any]) -> str:
    return " ".join(part.get("content", {}).get("text", "") for part in update.get("content", []) if isinstance(part, dict))


def _citation(summary: str) -> tuple[str | None, int | None, str]:
    match = re.search(r"\[memory:(m-[0-9a-f]{16})@([0-9]+)\] · ([a-z]+),", summary)
    return (match.group(1), int(match.group(2)), match.group(3)) if match else (None, None, "unknown")


# --- operations: the one real action each non-user case input names in the run config -----------------------------------

async def _op_none(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The input describes a state the run already has (an unchanged file, a trusted workspace): nothing to do."""


async def _op_pause_store(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The store stalls (a paused container) while the next user input is saved: the save times out, unconfirmed."""
    rig.pending["paused"] = True


async def _op_model_says(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The assistant says the input's text (after a status turn the prefilter skips)."""
    rig.model.say_next = text
    await rig.host.say("carry on", f"p-{seq}")
    rig.observe(run, seq)


async def _op_cards_fail(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The client goes away after the commit: the next user input's cards cannot be delivered."""
    rig.pending["cards_fail"] = True


async def _op_reconnect(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new host process and session on the same workspace and config: only the durable backlog carries over."""
    backlog = getattr(rig.host.state, "memory_backlog", None)
    pending = len(backlog.pending()) if backlog is not None else 0
    for _ in range(pending):
        run.add("notice.backlogged")
    rig.host = Host(rig, rig.host.workspace, rig.host.config)
    await rig.host.open()
    await rig.host.say("carry on", f"p-{seq}")
    rig.observe(run, seq)


async def _op_new_session(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """A new session on the same host: no conversation RAM, the same store."""
    rig.host = Host(rig, rig.host.workspace, rig.host.config)
    await rig.host.open()


async def _op_tool_output(rig: Rig, run: Run, seq: int, text: str, kind: str = "document", **_: Any) -> None:
    """Text from a tool or document enters the session's completed work as host evidence of that kind."""
    await _submit_work(rig, run, seq, text, (Evidence(f"ev-{seq}", kind, kind == "web"),))


async def _op_agent_work(rig: Rig, run: Run, seq: int, text: str, lesson: str = "", evidence: str = "", **_: Any) -> None:
    """The agent finished verified work (host-issued evidence); the extraction stand-in proposes the case's lesson from it."""
    if lesson:
        rig.extraction.lessons.append(lesson)
    await _submit_work(rig, run, seq, text, (Evidence(evidence or f"ev-{seq}", "verification"),))


async def _submit_work(rig: Rig, run: Run, seq: int, text: str, evidence: tuple[Evidence, ...]) -> None:
    extractor = rig.host.extractor
    turn = f"{rig.host.session}:work-{seq}"
    extractor.submit(TurnInput(turn, "project", (UserBlock(f"{turn}:user", "carry on"),), CompletedWork(text, evidence), (), True,
                               rig.extraction, lambda *_a: None))
    rig.observe(run, seq)


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


class _Later:
    """The `time` module as the host's continuity reads it, `seconds` later: time passing for the host, nothing re-dated."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def time(self) -> float:
        return time.time() + self.seconds

    def __getattr__(self, name: str) -> Any:
        return getattr(time, name)


async def _op_clock(rig: Rig, run: Run, seq: int, text: str, days: float = 0, **_: Any) -> None:
    """`days` pass: from now on the host's continuity clock reads that much later (run_case puts it back); a new session begins."""
    from optimus.context import memory_continuity

    passed = getattr(memory_continuity.time, "seconds", 0)
    memory_continuity.time = _Later(passed + days * 24 * 3600)  # type: ignore[assignment]
    await _op_new_session(rig, run, seq, text)


async def _op_crash(rig: Rig, run: Run, seq: int, text: str, **_: Any) -> None:
    """The host process dies during a turn after an earlier one settled: its in-flight turn is abandoned unsettled."""
    rig.pending["crash"] = True


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
    rig.observe(run, seq)


async def _op_compact(rig: Rig, run: Run, seq: int, text: str, turns: int = 3, **_: Any) -> None:
    """The context is compacted: status turns push the earlier ones past the attachment's tail, so the host's own compaction
    puts a summary in their place and hands their raw user text to extraction."""
    for n in range(turns):
        await rig.host.say("carry on", f"compact-{seq}-{n}")
        rig.observe(run, seq)


async def _op_prior_off(rig: Rig, run: Run, seq: int, text: str, said: str = "I would probably go with tabs.", **_: Any) -> None:
    """An earlier session said `said` (D9 sent it off), then ended: its RAM-only source text went with it."""
    await rig.host.say(said, f"prior-{seq}")
    rig.observe(run, seq)
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
        rig.observe(run, seq)


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
    rig.observe(run, seq)
    rig.store.lose_volume()
    await _op_new_session(rig, run, seq, text)
    await rig.host.say_confirming(_resolve("/memory restore {gen} --map", rig), f"p-{seq}-again", "allow")
    rig.observe(run, seq)


OPS: Mapping[str, Callable[..., Any]] = {name[4:]: value for name, value in globals().items() if name.startswith("_op_")}


# --- trace ---------------------------------------------------------------------------------------------------------------

def to_trace(case: GoldenCase, run: Run, named: Mapping[str, str], items: Mapping[str, Any], *, source_id: str, config_id: str,
             reverify: Sequence[tuple[str, int]] = (), history: Mapping[str, Sequence[Mapping[str, Any]]] = {}) -> ObservedTrace:
    """The grader's trace from what the run observed. `named` is case key -> the item the case input declared for that key
    created; `items` is the store's final state of every item the run touched; `history` is each named item's versions as
    the store lists them."""
    key_of = {item: key for key, item in named.items()}
    events: list[TraceEvent] = []
    for observation in run.observations:
        name = EVENT_OF.get(observation.kind)
        if name is None:
            continue
        key = key_of.get(observation.item or "")
        events.append(TraceEvent(seq=len(events), type=name, memory_key=key, project_id=case.project_id if key else None,
                                 version=observation.version, rotation_id=None))
    stale = {item for item, _version in reverify}
    state = []
    for item, row in sorted(items.items()):
        if item not in key_of:
            continue
        versions = sorted(history.get(item) or [{"version": row.version, "action": row.action, "status": row.status, "trust": row.trust,
                                           "kind": row.kind}], key=lambda entry: entry["version"])
        if versions[0]["action"] in ("withdraw", "tombstone"):
            # A restore that re-applies a recorded withdrawal or purge publishes only that entry; it covers every version below.
            versions = [{**versions[0], "version": n} for n in range(1, versions[0]["version"])] + versions
        for entry, status in zip(versions, version_statuses(versions), strict=True):
            latest = entry["version"] == row.version
            state.append(MemoryStateObservation(
                key=key_of[item], project_id=case.project_id, version=entry["version"], trust=_origin(entry["trust"], entry["kind"]),
                status=_status(entry["trust"], status, stale=latest and item in stale), off=entry["trust"] == "off",
                supersedes=entry["version"] - 1 if entry["action"] == "update" else None))
    served = [MemoryRef(memory_id=key_of[item], version=version, project_id=case.project_id)
              for item, version in (run.served[-1] if run.served else []) if item in key_of]
    needed = (*case.required_events, *case.prohibited_events)
    missing = tuple(sorted({name for name in needed if name.split(":")[0] not in OBSERVABLE}))
    return ObservedTrace(
        schema="plan12-memory-trace/1", case_id=case.case_id, case_version=case.version, source_id=source_id, config_id=config_id,
        events=tuple(events), evidence=(), served_memory=tuple(served), memory_state=tuple(state),
        answer=AnswerObservation(action="answer", claims=(), supported_by=(), support_extracted=False, citations=(), judge_status="uncertain"),
        attempts=(), provenance=(), reported_cost=ReportedCost(known_usd=Decimal("0"), complete=True, savings=None),
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


_LIVE = ("active", "reverify", "conflicted")


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


async def drive(rig: Rig, case: GoldenCase, steps: Mapping[int, Sequence[Any]], keys: Mapping[int, Sequence[str]], run: Run) -> None:
    await rig.host.open()
    for item in case.inputs:
        step = list(steps.get(item.seq, ["say"] if item.actor == "user" else []))
        if not step:
            raise NotImplementedError(f"{case.case_id}: input {item.seq} ({item.actor}) names no operation in the run config")
        name, options = step[0], (step[1] if len(step) > 1 else {})
        run.steps.append(f"{item.seq}:{item.actor}:{name}")
        if name in ("say", "confirm"):
            text = _resolve(options.get("text", item.text or ""), rig)
            rig.pending["said"] = True
            if options.get("cards_fail"):  # the client goes away after the commit: this input's cards cannot be delivered
                rig.host.outbound.__class__ = _CardsFail
            if options.get("pause"):  # the store stalls (a paused container) while this input is saved
                with rig.store.paused():
                    await rig.host.say(text, f"p-{item.seq}")
            elif name == "confirm":
                await rig.host.say_confirming(text, f"p-{item.seq}", options.get("choice", "allow"))
            else:
                if text.strip() == "/welcome":
                    rig.pending["welcome_requested"] = True
                await rig.host.say(text, f"p-{item.seq}")
            if rig.host.outbound.__class__ is _CardsFail:
                rig.host.outbound.__class__ = RecordingOutboundChannel
            rig.observe(run, item.seq)
        else:
            await OPS[name](rig, run, item.seq, item.text or "", **options)
        for seq, named in keys.items():
            created = [i for i, s in run.created_by.items() if s == seq]  # in the order the store appended them
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


def run_case(store: Store, base: Path, case: GoldenCase, entry: Mapping[str, Any], *, source_id: str, config_id: str) -> dict[str, Any]:
    rig = Rig(store, base, case.case_id)
    run = Run()
    keys = {int(seq): [key] if isinstance(key, str) else list(key) for seq, key in entry.get("keys", {}).items()}
    steps = {int(seq): step for seq, step in entry.get("steps", {}).items()}
    started = time.monotonic()
    error = cause = None
    from optimus.context import memory_continuity

    try:
        asyncio.run(drive(rig, case, steps, keys, run))
    except Exception as failure:  # noqa: BLE001 - a run that could not finish is reported with its cause, never graded PASS
        error, cause = f"{type(failure).__name__}: {failure}", traceback.format_exc()
    finally:
        memory_continuity.time = time  # type: ignore[assignment]  # the clock an `_op_clock` moved
    reverify = _reverify(rig.host, None) if error is None else []
    items, history = final_items(rig) if error is None else ({}, {})
    trace = to_trace(case, run, rig.items, items, source_id=source_id, config_id=config_id, reverify=reverify, history=history)
    if error is not None:
        trace = trace.model_copy(update={"missing_coverage": (*trace.missing_coverage, f"run did not finish: {error}"), "coverage_complete": False})
    verdict = grade_trace(case, trace)
    unrun = sorted({UNRUN_EVENTS[n.split(":")[0]] for n in case.required_events if n.split(":")[0] in UNRUN_EVENTS})
    return {"case_id": case.case_id, "steps": run.steps, "error": error, "cause": cause, "seconds": round(time.monotonic() - started, 1),
            "unrun_owner": unrun, "qualification": qualification_view(case, verdict, unrun),
            "trace": json.loads(trace.model_dump_json(by_alias=True)), "verdict": json.loads(verdict.model_dump_json())}


PAID = "paid Zed sessions M3-ZED-OFF/ON/RETURN"


def qualification_view(case: GoldenCase, verdict: Any, unrun: Sequence[str]) -> dict[str, Any]:
    """What this zero-paid run decides (Codex CP4 gate 1, Q3); the grader's own verdict is kept beside it, unchanged. The
    authority and cost layers stand on what the host and store did. The answer layer is UNRUN: the stand-in model neither
    answers nor abstains on evidence; the paid Zed sessions own it. So is the retrieval layer of a case that requires retrieved
    evidence: the stand-in runs no tools, so none is retrieved. A case is therefore never PASS here: at best INCONCLUSIVE, with
    any FAIL of a decided layer kept. A case whose required events the product cannot show yet (decay, #235 M6) is UNRUN whole,
    with that owner: its other layers rest on the same missing behaviour."""
    layers = {name: layer.status for name, layer in verdict.layers.items()}
    owners = {"answer": PAID}
    if case.required_evidence:
        owners["retrieval"] = PAID
    layers.update({name: "UNRUN" for name in owners})
    if unrun:
        return {"status": "UNRUN", "layers": layers, "owners": {**owners, "case": ", ".join(unrun)}}
    return {"status": "FAIL" if "FAIL" in layers.values() else "INCONCLUSIVE", "layers": layers, "owners": owners}


def load_cases(path: Path) -> dict[str, GoldenCase]:
    document = json.loads(path.read_text(encoding="utf-8"))
    return {raw["case_id"]: GoldenCase.model_validate(raw) for raw in document["cases"]}


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
            print(case_id, result["qualification"]["status"], result["qualification"]["layers"], result["error"] or "", flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    args.output.mkdir(parents=True, exist_ok=True)
    document = {"schema": SCHEMA, "source": source, "dirty": dirty, "config_id": config["config_id"], "results": results}
    (args.output / "results.json").write_bytes((json.dumps(document, indent=1, ensure_ascii=True) + "\n").encode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
