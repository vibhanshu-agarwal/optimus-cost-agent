"""Plan 12.2 Task 10: one full-set config publication for mode and strategy (design spec 10; Task 1
contracts 5).

Every response and update carries the full current `configOptions`. The strategy select (wire option
`id` and setter `configId` both "context_strategy", category `_context_strategy`) exists only for an
attached session and stays visible through an engine fault. A strategy-only change sends no
`current_mode_update`. Setters share one per-session lock and one publication state: a committed
change whose updates were not confirmed stays pending and is republished by the next setter, and a
send made at an older revision can never clear a newer pending state. Setters never wait for a turn.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from optimus.acp.errors import AcpOutboundError
from optimus.acp.session_config import (
    SLIDING_DESCRIPTION,
    STRATEGY_CATEGORY,
    STRATEGY_CONFIG_ID,
    ConfigPublication,
    SessionConfigSnapshot,
    build_session_config_options,
)
from tests.unit.acp.test_context_engine_admission import (
    FlakyEngine,
    Runner,
    SummarizerCall,
    make_adapter,
    make_attachment,
    new_session,
    prompt,
    prompt_request,
    rpc,
    session_of,
)

_SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "fixtures" / "acp" / "acp-v1-schema.json").read_text(encoding="utf-8"))


def assert_schema(definition: str, payload: dict[str, Any]) -> None:
    validator = Draft202012Validator({"$defs": _SCHEMA["$defs"], "$ref": f"#/$defs/{definition}"})
    errors = [error.message for error in validator.iter_errors(payload)]
    assert errors == [], errors


def set_option(session_id: str, config_id: str, value: Any, request_id: str = "set") -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "session/set_config_option",
        "params": {"sessionId": session_id, "configId": config_id, "value": value},
    }


def set_mode(session_id: str, mode_id: str, request_id: str = "mode") -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": mode_id}}


def config_updates(outbound) -> list[dict[str, Any]]:
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    return [u for u in updates if u["sessionUpdate"] in {"current_mode_update", "config_option_update"}]


def by_id(options: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {option["id"]: option for option in options}


# --- The builder ----------------------------------------------------------------------------------


def test_an_absent_engine_publishes_only_the_mode_option():
    options = build_session_config_options(SessionConfigSnapshot(mode_id="agent", strategy=None))

    assert [option["id"] for option in options] == ["mode"]
    assert_schema("SetSessionConfigOptionResponse", {"configOptions": options})


def test_an_attached_session_publishes_mode_and_strategy():
    options = build_session_config_options(SessionConfigSnapshot(mode_id="chat", strategy="compaction"))

    assert [option["id"] for option in options] == ["mode", STRATEGY_CONFIG_ID]
    strategy = by_id(options)[STRATEGY_CONFIG_ID]
    assert (strategy["category"], strategy["type"], strategy["currentValue"]) == (STRATEGY_CATEGORY, "select", "compaction")
    assert [choice["value"] for choice in strategy["options"]] == ["compaction", "hybrid", "sliding_window"]
    choices = {choice["value"]: choice for choice in strategy["options"]}
    assert choices["sliding_window"]["description"] == SLIDING_DESCRIPTION
    assert SLIDING_DESCRIPTION == (
        "Keeps only the newest complete ordinary turns that fit. Older ordinary conversation content is dropped from model context."
    )
    assert by_id(options)["mode"]["currentValue"] == "chat"
    assert_schema("SetSessionConfigOptionResponse", {"configOptions": options})


@pytest.mark.parametrize("bad", [{"mode_id": "plan", "strategy": None}, {"mode_id": "agent", "strategy": "auto"}])
def test_the_snapshot_refuses_values_outside_the_choices(bad):
    with pytest.raises(ValueError):
        SessionConfigSnapshot(**bad)


def test_an_older_send_never_clears_a_newer_pending_state():
    state = ConfigPublication()
    first = state.commit(mode_changed=True)
    assert state.pending_updates() == ("current_mode_update", "config_option_update")
    second = state.commit(mode_changed=False)

    state.confirmed(first)  # a send made at the older revision
    assert state.pending_updates() == ("current_mode_update", "config_option_update")

    state.confirmed(second)
    assert state.pending_updates() == ()


def test_a_strategy_only_change_pends_only_the_full_set():
    state = ConfigPublication()
    state.commit(mode_changed=False)
    assert state.pending_updates() == ("config_option_update",)


# --- Through the ACP host -------------------------------------------------------------------------


async def test_new_sessions_advertise_the_full_set(tmp_path):
    absent, _, _ = make_adapter(tmp_path, None)
    attached, _, _ = make_adapter(tmp_path, make_attachment())
    absent_result = (await rpc(absent, {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}))["result"]
    attached_result = (await rpc(attached, {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}))["result"]

    assert [option["id"] for option in absent_result["configOptions"]] == ["mode"]
    assert [option["id"] for option in attached_result["configOptions"]] == ["mode", STRATEGY_CONFIG_ID]
    assert by_id(attached_result["configOptions"])[STRATEGY_CONFIG_ID]["currentValue"] == "compaction"
    assert_schema("NewSessionResponse", attached_result)


async def test_a_strategy_change_publishes_the_full_set_without_a_mode_update(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path, mode="chat")
    outbound.notifications.clear()

    response = await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "sliding_window"))

    options = response["result"]["configOptions"]
    assert by_id(options)[STRATEGY_CONFIG_ID]["currentValue"] == "sliding_window"
    assert by_id(options)["mode"]["currentValue"] == "chat"  # the other picker is preserved
    updates = config_updates(outbound)
    assert [u["sessionUpdate"] for u in updates] == ["config_option_update"]
    assert updates[0]["configOptions"] == options
    assert session_of(adapter, session_id).context_strategy == "sliding_window"
    assert_schema("SetSessionConfigOptionResponse", response["result"])
    [notification] = [n for n in outbound.notifications if n["params"]["update"]["sessionUpdate"] == "config_option_update"]
    assert_schema("SessionNotification", notification["params"])


@pytest.mark.parametrize("via", ["set_mode", "set_config_option"])
async def test_a_mode_change_preserves_the_strategy_option(tmp_path, via):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path)
    await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid", "s"))
    outbound.notifications.clear()

    request = set_mode(session_id, "chat") if via == "set_mode" else set_option(session_id, "mode", "chat")
    await rpc(adapter, request)

    updates = config_updates(outbound)
    assert [u["sessionUpdate"] for u in updates] == ["current_mode_update", "config_option_update"]
    assert by_id(updates[1]["configOptions"])[STRATEGY_CONFIG_ID]["currentValue"] == "hybrid"


async def test_an_absent_engine_strategy_setter_is_an_unknown_option(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, None)
    session_id = await new_session(adapter, tmp_path)
    outbound.notifications.clear()

    response = await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "sliding_window"))

    assert response["error"]["message"] == "unknown config option"
    assert config_updates(outbound) == []
    assert session_of(adapter, session_id).context_strategy is None


@pytest.mark.parametrize("value", ["auto", "", None, 3, "SLIDING_WINDOW"])
async def test_an_invalid_strategy_changes_nothing(tmp_path, value):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path)
    outbound.notifications.clear()

    response = await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, value))

    assert "error" in response
    assert config_updates(outbound) == []
    assert session_of(adapter, session_id).context_strategy == "compaction"


@pytest.mark.parametrize("failing", ["current_mode_update", "config_option_update"])
async def test_a_half_sent_mode_change_is_republished_by_the_next_strategy_setter(tmp_path, failing):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path)
    original = outbound.notify
    failures = {failing: 1}

    async def notify(method, params, *, require_flushed=False):
        kind = params.get("update", {}).get("sessionUpdate")
        if failures.get(kind):
            failures[kind] -= 1
            raise AcpOutboundError(code=-32603, message="write failed")
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    with pytest.raises(AcpOutboundError):
        await rpc(adapter, set_mode(session_id, "chat"))
    assert session_of(adapter, session_id).execution_mode.value == "CHAT"  # committed, though unconfirmed
    outbound.notifications.clear()

    await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid"))

    # The pending mode change is republished with the full current set, then the state is clean.
    updates = config_updates(outbound)
    assert [u["sessionUpdate"] for u in updates] == ["current_mode_update", "config_option_update"]
    options = by_id(updates[1]["configOptions"])
    assert (options["mode"]["currentValue"], options[STRATEGY_CONFIG_ID]["currentValue"]) == ("chat", "hybrid")
    outbound.notifications.clear()
    await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid", "again"))
    assert config_updates(outbound) == []  # synchronized: repeating a value is idempotent


async def test_a_half_sent_strategy_change_is_republished_without_a_mode_update(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path)
    original = outbound.notify
    failures = {"config_option_update": 1}

    async def notify(method, params, *, require_flushed=False):
        kind = params.get("update", {}).get("sessionUpdate")
        if failures.get(kind):
            failures[kind] -= 1
            raise AcpOutboundError(code=-32603, message="write failed")
        await original(method, params, require_flushed=require_flushed)

    outbound.notify = notify  # type: ignore[method-assign]
    with pytest.raises(AcpOutboundError):
        await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid"))
    outbound.notifications.clear()

    await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid", "retry"))

    assert [u["sessionUpdate"] for u in config_updates(outbound)] == ["config_option_update"]


async def test_a_setter_during_maintenance_changes_only_the_next_turn(tmp_path):
    entered, release = threading.Event(), threading.Event()

    def block() -> None:
        entered.set()
        assert release.wait(5)

    summarizer = SummarizerCall()
    runner = Runner()
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(summarizer=summarizer), runner)
    session_id = await new_session(adapter, tmp_path, mode="chat")
    for n in range(3):
        await prompt(adapter, outbound, session_id, f"Earlier prompt {n}", f"p{n}")
    summarizer._during = block  # noqa: SLF001

    turn = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Now", "now")))
    assert await asyncio.to_thread(entered.wait, 5)
    response = await asyncio.wait_for(rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "sliding_window")), timeout=2)
    release.set()
    await asyncio.wait_for(turn, timeout=5)

    assert by_id(response["result"]["configOptions"])[STRATEGY_CONFIG_ID]["currentValue"] == "sliding_window"
    assert runner.kwargs[-1]["context_packer"].admitted.strategy == "compaction"
    summarizer._during = None  # noqa: SLF001
    await prompt(adapter, outbound, session_id, "Next", "next")
    assert runner.kwargs[-1]["context_packer"].admitted.strategy == "sliding_window"


async def test_a_setter_while_permission_is_pending_does_not_wait_for_the_turn(tmp_path):
    adapter, outbound, runner = make_adapter(tmp_path, make_attachment())
    session_id = await new_session(adapter, tmp_path)

    turn = asyncio.create_task(rpc(adapter, prompt_request(session_id, "Change it", "p1")))
    permission = await asyncio.wait_for(outbound.wait_for_request("session/request_permission"), timeout=5)
    response = await asyncio.wait_for(rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid")), timeout=2)
    outbound.respond(permission["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    await asyncio.wait_for(turn, timeout=5)

    assert "result" in response
    assert runner.requests[-1].approval.approved  # the turn applied its admitted plan


async def test_an_engine_fault_leaves_the_strategy_picker_visible(tmp_path):
    adapter, outbound, _ = make_adapter(tmp_path, make_attachment(engine=FlakyEngine(failures=10)))
    session_id = await new_session(adapter, tmp_path, mode="chat")
    await prompt(adapter, outbound, session_id, "hello", "p1")  # falls back: the engine is unavailable

    response = await rpc(adapter, set_option(session_id, STRATEGY_CONFIG_ID, "hybrid"))

    assert by_id(response["result"]["configOptions"])[STRATEGY_CONFIG_ID]["currentValue"] == "hybrid"
