"""#643: a committed memory change's notice stays recoverable when the durable notice backlog cannot be written. The real adapter,
the real `NoticeBacklog` on a temp config folder, and the real store stand-in; the failure is injected where the backlog writes
its file (`memory_recovery._durable_json`), as a full disk would refuse it."""

from __future__ import annotations

import asyncio
import errno
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from context_engine.memory_contracts import MemoryNotice
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.context import memory_recovery as mr
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment, new_session, prompt_request, rpc
from tests.unit.acp.test_memory_commands import _events_any, _PurgeSource, _updates
from tests.unit.context.test_authored_memory import _adapter
from tests.unit.optimus_gateway.test_memory_store_purge import store as purge_store


class _Outbound(RecordingOutboundChannel):
    """A client connection whose memory cards can be made to fail (a dropped connection) and then work again."""

    cards_fail = False

    async def notify(self, method: str, params: dict[str, Any], **kwargs: Any) -> Any:
        if self.cards_fail and params.get("update", {}).get("sessionUpdate") == "tool_call":
            raise ConnectionError("the client went away")
        return await super().notify(method, params, **kwargs)


class _Disk:
    """The notice backlog's file writes: refused with ENOSPC while `full`; every other durable write is untouched."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.full = False
        real = mr._durable_json

        def write(path: Path, value: Any) -> None:
            if self.full and path.parent.name == "memory-notices":
                raise OSError(errno.ENOSPC, "No space left on device", str(path))
            real(path, value)

        monkeypatch.setattr(mr, "_durable_json", write)


class _Host:
    """One host process: its adapter, its client connection, and the project's backlog as this process shares it."""

    def __init__(self, tmp_path: Path, service: Any, *, shared: bool = True) -> None:
        self.outbound = _Outbound()
        self.reports: list[Any] = []
        root = tmp_path / "config"

        def factory(_workspace: Path, **kwargs: Any) -> _PurgeSource:
            self.reports.append(kwargs["report"])  # the adapter's own `_memory_report(session)` closure
            made = _PurgeSource(_adapter(service))
            made.notices = mr.NoticeBacklog.shared(root, "p-1") if shared else mr.NoticeBacklog(root, "p-1")
            return made

        self.adapter = AcpDuplexAdapter(runner=checked_agent_runner(Runner()), workspace_root=tmp_path,
                                        sessions=InMemoryAcpSpecSessionStore(), outbound=self.outbound,
                                        context_attachment=make_attachment(), memory_extractor_factory=factory)

    def cards(self) -> list[str]:
        return [u["toolCallId"] for u in _updates(self.outbound) if u["sessionUpdate"] == "tool_call"]


def _file(tmp_path: Path) -> list[dict[str, Any]]:
    return mr.NoticeBacklog(tmp_path / "config", "p-1").pending()  # a fresh instance reads only what is on disk


def _forget_shared(tmp_path: Path) -> None:
    """A host restart: the next process starts with no shared instance, only the file."""
    with mr._SHARED_LOCK:
        mr._SHARED.pop(mr.NoticeBacklog(tmp_path / "config", "p-1").path, None)


def test_a_delivered_command_notice_is_shown_once_and_leaves_no_backlog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Today's good path, pinned: the backlog write succeeds, the card is delivered once, and its record is removed."""
    _Disk(monkeypatch)

    async def scenario() -> None:
        host = _Host(tmp_path, purge_store(tmp_path)[0])
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        response = await rpc(host.adapter, prompt_request(session_id, "/remember Never push to main.", "p-1"))
        assert "result" in response
        (card,) = host.cards()
        assert card.startswith("memory/") and _file(tmp_path) == []
        await rpc(host.adapter, prompt_request(session_id, "Hello there", "p-2"))
        assert host.cards() == [card]
    asyncio.run(scenario())


def test_a_command_notice_whose_backlog_write_and_card_both_fail_is_shown_at_the_next_turn(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex's #334 finding (command path): the change commits, the backlog refuses the record, and the card cannot be sent. The
    next turn of the same session, with the client back, shows the card once; nothing is written to the store again."""
    disk = _Disk(monkeypatch)

    async def scenario() -> None:
        service = purge_store(tmp_path)[0]
        host = _Host(tmp_path, service)
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full, host.outbound.cards_fail = True, True
        response = await rpc(host.adapter, prompt_request(session_id, "/remember Never push to main.", "p-1"))
        assert "error" in response and host.cards() == []
        events = _events_any(_adapter(service))
        host.outbound.cards_fail = False
        await rpc(host.adapter, prompt_request(session_id, "Hello there", "p-2"))
        (card,) = host.cards()
        assert card.startswith("memory/")
        await rpc(host.adapter, prompt_request(session_id, "And again", "p-3"))
        assert host.cards() == [card] and _events_any(_adapter(service)) == events
    asyncio.run(scenario())


def test_a_command_notice_whose_backlog_write_and_card_both_fail_is_shown_by_a_reopened_session(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same loss, seen from a new session of the project in the same host process: it shows the card once."""
    disk = _Disk(monkeypatch)

    async def scenario() -> None:
        host = _Host(tmp_path, purge_store(tmp_path)[0])
        first = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full, host.outbound.cards_fail = True, True
        assert "error" in await rpc(host.adapter, prompt_request(first, "/remember Never push to main.", "p-1"))
        host.outbound.cards_fail = False
        second = await new_session(host.adapter, tmp_path, mode="chat")
        await rpc(host.adapter, prompt_request(second, "Hello there", "p-2"))
        (card,) = host.cards()
        await rpc(host.adapter, prompt_request(first, "Back in the first session", "p-3"))
        assert host.cards() == [card]  # delivered once for the project, not once per session
    asyncio.run(scenario())


def _committed(tmp_path: Path, service: Any) -> MemoryNotice:
    """A real committed change in the store (made and delivered by a host whose disk works), as extraction would report it."""
    async def scenario() -> MemoryNotice:
        host = _Host(tmp_path, service, shared=False)
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        await rpc(host.adapter, prompt_request(session_id, "/remember Tests run with pytest -q.", "p-0"))
        ((item, version, *_),) = _events_any(_adapter(service))
        event = _adapter(service).read(item).event
        return MemoryNotice(event.event_id, item, version, "admit", "confirmed", "current")
    return asyncio.run(scenario())


def test_an_extraction_notice_whose_backlog_write_fails_is_shown_by_the_replacing_session(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex's #334 finding (extraction path): an extraction outcome commits, the backlog refuses its record, and the session is
    replaced before its next turn. The replacing session shows the card once."""
    disk = _Disk(monkeypatch)
    service = purge_store(tmp_path)[0]
    notice = _committed(tmp_path, service)

    async def scenario() -> None:
        host = _Host(tmp_path, service)
        first = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full = True
        host.reports[-1](SimpleNamespace(notices=[notice]))  # the extraction worker reports its committed outcome
        assert _file(tmp_path) == []
        host.adapter._sessions.remove(first)  # replaced before its next turn
        second = await new_session(host.adapter, tmp_path, mode="chat")
        await rpc(host.adapter, prompt_request(second, "Hello there", "p-1"))
        assert host.cards() == [f"memory/{notice.event_id}"]
    asyncio.run(scenario())


def test_a_command_notice_held_through_a_failed_write_survives_a_restart_once_a_retry_writes_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The acceptance: the write and the card fail; the disk recovers and the next turn's backlog read writes the held record while
    the client is still away; the host restarts. The new process shows the card once, and the store holds no second change."""
    disk = _Disk(monkeypatch)

    async def scenario() -> None:
        service = purge_store(tmp_path)[0]
        host = _Host(tmp_path, service)
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full, host.outbound.cards_fail = True, True
        assert "error" in await rpc(host.adapter, prompt_request(session_id, "/remember Never push to main.", "p-1"))
        assert _file(tmp_path) == []
        disk.full = False
        await rpc(host.adapter, prompt_request(session_id, "Hello there", "p-2"))  # the retry; the card still cannot be sent
        (record,) = _file(tmp_path)
        events = _events_any(_adapter(service))
        _forget_shared(tmp_path)
        restarted = _Host(tmp_path, service)
        session_id = await new_session(restarted.adapter, tmp_path, mode="chat")
        await rpc(restarted.adapter, prompt_request(session_id, "Hello again", "p-3"))
        await rpc(restarted.adapter, prompt_request(session_id, "And again", "p-4"))
        assert restarted.cards() == [f"memory/{record['event_id']}"]
        assert _file(tmp_path) == [] and _events_any(_adapter(service)) == events
    asyncio.run(scenario())


def test_an_extraction_notice_held_through_a_failed_write_survives_a_restart_once_a_retry_writes_it(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The extraction path's acceptance: the report's write fails, the disk recovers, another session's turn writes the held
    record while its card cannot be sent, the host restarts, and the new process shows the card once."""
    disk = _Disk(monkeypatch)
    service = purge_store(tmp_path)[0]
    notice = _committed(tmp_path, service)

    async def scenario() -> None:
        host = _Host(tmp_path, service)
        first = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full = True
        host.reports[-1](SimpleNamespace(notices=[notice]))
        host.adapter._sessions.remove(first)
        disk.full, host.outbound.cards_fail = False, True
        second = await new_session(host.adapter, tmp_path, mode="chat")
        await rpc(host.adapter, prompt_request(second, "Hello there", "p-1"))
        assert [record["event_id"] for record in _file(tmp_path)] == [notice.event_id]
        _forget_shared(tmp_path)
        restarted = _Host(tmp_path, service)
        session_id = await new_session(restarted.adapter, tmp_path, mode="chat")
        await rpc(restarted.adapter, prompt_request(session_id, "Hello again", "p-2"))
        await rpc(restarted.adapter, prompt_request(session_id, "And again", "p-3"))
        assert restarted.cards() == [f"memory/{notice.event_id}"] and _file(tmp_path) == []
    asyncio.run(scenario())


def test_a_delivered_notice_whose_removal_fails_is_not_shown_again_after_a_restart(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half of "without duplicates": the card is delivered but the removal's write fails, so the record stays in the
    file. The removal is held as a tombstone, a later turn writes it once the disk recovers, and a restarted host shows nothing."""
    disk = _Disk(monkeypatch)

    async def scenario() -> None:
        service = purge_store(tmp_path)[0]
        host = _Host(tmp_path, service)
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        backlog = mr.NoticeBacklog.shared(tmp_path / "config", "p-1")
        real_remove = backlog.remove

        def remove(event_ids: list[str]) -> None:  # the disk fills between the add and the removal
            disk.full = True
            real_remove(event_ids)

        monkeypatch.setattr(backlog, "remove", remove)
        assert "result" in await rpc(host.adapter, prompt_request(session_id, "/remember Never push to main.", "p-1"))
        (card,) = host.cards()
        assert len(_file(tmp_path)) == 1  # delivered, but still on disk
        monkeypatch.setattr(backlog, "remove", real_remove)
        await rpc(host.adapter, prompt_request(session_id, "Hello there", "p-2"))
        assert host.cards() == [card]  # never re-shown in this process while the removal is held
        disk.full = False
        await rpc(host.adapter, prompt_request(session_id, "And again", "p-3"))  # the retry writes the removal
        assert _file(tmp_path) == []
        _forget_shared(tmp_path)
        restarted = _Host(tmp_path, service)
        session_id = await new_session(restarted.adapter, tmp_path, mode="chat")
        await rpc(restarted.adapter, prompt_request(session_id, "Hello again", "p-4"))
        assert restarted.cards() == []
    asyncio.run(scenario())


def test_known_limit_a_notice_is_lost_when_every_write_fails_until_the_process_is_replaced(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """KNOWN LIMIT (#643, put to the operator): if the disk refuses every backlog write until the host process is replaced, no
    durable record of the notice exists, so the new process shows no card. The change itself is kept: `/memory` lists it."""
    disk = _Disk(monkeypatch)

    async def scenario() -> None:
        service = purge_store(tmp_path)[0]
        host = _Host(tmp_path, service)
        session_id = await new_session(host.adapter, tmp_path, mode="chat")
        disk.full, host.outbound.cards_fail = True, True
        assert "error" in await rpc(host.adapter, prompt_request(session_id, "/remember Never push to main.", "p-1"))
        await rpc(host.adapter, prompt_request(session_id, "Hello there", "p-2"))  # its retry fails too
        _forget_shared(tmp_path)
        restarted = _Host(tmp_path, service)
        session_id = await new_session(restarted.adapter, tmp_path, mode="chat")
        await rpc(restarted.adapter, prompt_request(session_id, "/memory", "p-3"))
        assert restarted.cards() == []
        texts = [u["content"]["text"] for u in _updates(restarted.outbound) if u["sessionUpdate"] == "agent_message_chunk"]
        assert any("active " + chr(0xB7) + " Never push to main" in text for text in texts), texts  # listed, active
    asyncio.run(scenario())
