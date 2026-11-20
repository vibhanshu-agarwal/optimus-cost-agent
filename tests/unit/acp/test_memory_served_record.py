"""#514: each memory-on turn's trace names how its memory read ended, the item versions it was served and the store position the
read came from, never memory text. Through the real adapter, host store and Gateway store (on the in-memory Redis stand-in)."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from optimus.acp import spec
from optimus.acp.debug_trace import configure_debug_trace, resolve_debug_log_path
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel
from optimus.context import memory_serving
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_context_engine_admission import Runner, make_attachment, new_session, prompt_request, rpc
from tests.unit.acp.test_memory_commands import _events_any, _PurgeSource
from tests.unit.context.test_authored_memory import _adapter
from tests.unit.context.test_memory_serving import _item
from tests.unit.optimus_gateway.test_memory_store_purge import store as purge_store

RULE = "Never push to main."


def _records(log: Path) -> list[dict[str, Any]]:
    lines = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
    return [line["data"] for line in lines if line["message"] == "memory served"]


def _turn_with(tmp_path: Path, failure: Any = None) -> tuple[list[dict[str, Any]], str, Path]:
    """One remembered rule, then one question whose read either works or meets `failure` (patched onto the listing)."""
    log = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log)
    store = _adapter(purge_store(tmp_path)[0])

    async def scenario() -> str:
        adapter = AcpDuplexAdapter(runner=checked_agent_runner(Runner()), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(),
                                   outbound=RecordingOutboundChannel(), context_attachment=make_attachment(),
                                   memory_extractor_factory=lambda _workspace, **_kwargs: _PurgeSource(store))
        session_id = await new_session(adapter, tmp_path, mode="chat")
        await rpc(adapter, prompt_request(session_id, f"/remember {RULE}", "p-1"))
        ((item, *_),) = _events_any(store)
        if failure is not None:
            store.page = failure  # type: ignore[method-assign]
        response = await rpc(adapter, prompt_request(session_id, "May I push?", "p-2"))
        assert response["result"]["stopReason"] == "end_turn", "memory never stops the turn"
        return str(item)

    item = asyncio.run(scenario())
    return _records(log), item, log


def test_a_served_read_names_each_item_version_and_the_store_position(tmp_path: Path) -> None:
    (record,), item, log = _turn_with(tmp_path)
    assert record["source"] == "turn" and record["outcome"] == "served"
    assert record["served"] == [f"{item}@1"] and record["complete"] is True
    assert record["omitted_protected"] == record["omitted_optional"] == 0 and record["reverify"] == record["elsewhere"] == []
    (watermark,) = record["watermarks"]
    major, minor = watermark.split("-")
    assert int(major) > 0 and minor.isdigit(), "the confirmed stream position the listing came from, past the remembered rule"
    assert RULE not in log.read_text(encoding="utf-8"), "memory text never reaches the trace"


def test_a_failed_read_says_it_served_nothing_after_an_error(tmp_path: Path) -> None:
    (record,), _item_id, _log = _turn_with(tmp_path, failure=lambda *_a, **_k: (_ for _ in ()).throw(OSError("down")))
    assert record == {"run_id": record["run_id"], "source": "turn", "outcome": "error"} and record["run_id"]


def test_a_slow_read_says_it_served_nothing_after_the_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec, "MEMORY_SERVE_SECONDS", 0.05)

    def slow(*_a: Any, **_k: Any) -> Any:
        time.sleep(0.5)
        raise OSError("too late")

    (record,), _item_id, _log = _turn_with(tmp_path, failure=slow)
    assert record["outcome"] == "timeout" and "served" not in record


def test_the_brief_read_the_turn_reuses_is_recorded_as_the_briefs(tmp_path: Path) -> None:
    log = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log)
    served = memory_serving.select([_item(1, statement=RULE)], watermarks=("17-0",))
    notified: list[Any] = []

    async def notify(*args: Any, **kwargs: Any) -> None:
        notified.append(args)

    owner = SimpleNamespace(_outbound=SimpleNamespace(notify=notify))
    session = SimpleNamespace(memory_commands=SimpleNamespace(served=lambda: served),
                              continuity=SimpleNamespace(first_response_brief=lambda serve: f"Welcome back: {len(serve().items)} item"))
    turn = SimpleNamespace(run_id="session-0123456789abcdef0123456789abcdef:3", session_id="s", served_memory=None, brief=None,
                           turn_control=SimpleNamespace(transport_abandoned=lambda: False))
    asyncio.run(AcpDuplexAdapter._emit_brief(owner, session, turn))  # type: ignore[arg-type]
    assert turn.served_memory is served and notified
    (record,) = _records(log)
    assert record["source"] == "brief" and record["outcome"] == "served" and record["served"] == [f"{served.items[0].item}@1"]
    assert record["watermarks"] == ["17-0"] and record["run_id"] == turn.run_id
    assert RULE not in log.read_text(encoding="utf-8")


def test_a_watermark_of_another_shape_is_never_written(tmp_path: Path) -> None:
    from optimus.acp.debug_trace import log_memory_served

    log = resolve_debug_log_path(workspace_root=tmp_path)
    configure_debug_trace(enabled=True, log_path=log)
    log_memory_served(run_id="session-0123456789abcdef0123456789abcdef:1", source="turn", outcome="served",
                      served=memory_serving.select([], watermarks=("Never push to main.",)))
    (record,) = _records(log)
    assert record["watermarks"] == ["unrecognized"]
