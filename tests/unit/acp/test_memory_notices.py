"""Plan 12.11 Task 1: host memory notices render only what the store confirmed, under a reserved id, with labels that
render as themselves."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from context_engine.memory_contracts import MemoryNotice
from optimus.acp import memory_notices
from tests.support import child_keyring

_SAVED = MemoryNotice("e-1", "m-0123456789abcdef", 1, "admit", "confirmed", "current")
_PENDING = MemoryNotice("e-2", "m-0123456789abcdef", 1, "admit", "unconfirmed", "pending")


@pytest.mark.parametrize("hostile", ["\u202eevil", "a\u200bb", "x\x07y", "\ufeffz", "\u2066iso\u2069", "line\nbreak", "tab\there"])
def test_a_label_loses_controls_bidi_and_zero_width_marks(hostile: str) -> None:
    label = memory_notices.escape_label(hostile)
    assert all(ord(c) >= 32 for c in label) and not any(c in label for c in "\u202e\u200b\ufeff\u2066\u2069")


def test_markdown_in_a_label_is_escaped_not_stripped() -> None:
    assert memory_notices.escape_label("**bold** [a](b) `c` <i> #h") == r"\*\*bold\*\* \[a\]\(b\) \`c\` \<i\> \#h"


@pytest.mark.parametrize(("text", "shown"), [("see http://x.test", r"see http\[:\]//x\.test"), ("HTTPS://a", r"HTTPS\[:\]//a"),
                                             ("www.example.test", r"www\[\.\]example\.test")])
def test_a_web_address_in_a_label_cannot_become_a_link(text: str, shown: str) -> None:
    assert memory_notices.escape_label(text) == shown


def test_a_long_label_is_bounded_before_escaping() -> None:
    label = memory_notices.escape_label("x" * 500)
    assert len(label) == memory_notices.MAX_LABEL_CHARS and label.endswith("\u2026")


def test_only_a_confirmed_save_says_remembered() -> None:
    assert memory_notices.headline(_SAVED) == "Remembered"
    assert "Remembered" not in memory_notices.headline(_PENDING) and "not confirmed" in memory_notices.headline(_PENDING)
    assert "Remembered" not in memory_notices.appended_text(_PENDING, "x")


def test_a_card_uses_the_reserved_id_and_carries_the_citation() -> None:
    update = memory_notices.card("s-1", _SAVED, "**x**")["update"]
    assert update["toolCallId"] == "memory/e-1" and memory_notices.is_memory_card(update["toolCallId"])
    assert update["title"] == r"Remembered: \*\*x\*\*" and update["status"] == "completed"
    assert "[memory:m-0123456789abcdef@1]" in json.dumps(update)
    assert memory_notices.card("s-1", _PENDING, "x")["update"]["status"] == "failed"
    assert not memory_notices.is_memory_card("call_abc") and not memory_notices.is_memory_card(None)


def test_the_probe_answers_without_a_network_and_emits_the_real_cards(tmp_path: Path) -> None:
    """Z0's agent, run as Zed runs it, over stdio, with sockets refused: the session, the first-response brief, cards and `/welcome`."""
    log = tmp_path / "z0.jsonl"
    lines = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": 1}},
             {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}},
             {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": "z0-session", "prompt": [{"type": "text", "text": "hi"}]}},
             {"jsonrpc": "2.0", "id": 4, "method": "session/prompt", "params": {"sessionId": "z0-session", "prompt": [{"type": "text", "text": "/welcome"}]}}]
    # asyncio's own self-pipe connects to a port this process bound; anything else, and any name lookup, is refused
    no_network = (
        "import sys\nbound = []\n"
        "def guard(event, args):\n"
        "    if event == 'socket.bind': bound.append(args[0])\n"
        "    elif event == 'socket.getaddrinfo': raise OSError('name lookup refused in Z0')\n"
        "    elif event == 'socket.connect' and (args[1][0] != '127.0.0.1' or args[1][1] not in {s.getsockname()[1] for s in bound}):\n"
        "        raise OSError('network refused in Z0')\n"
        "sys.addaudithook(guard)\n"
    )
    probe = Path(__file__).resolve().parents[3] / "tools" / "plan12_memory" / "m3_notice_probe.py"
    run = subprocess.run([sys.executable, "-c", no_network + f"import runpy, sys; sys.argv = ['probe', '--log', {str(log)!r}]; runpy.run_path({str(probe)!r}, run_name='__main__')"],
                         input="".join(json.dumps(line) + "\n" for line in lines).encode(), capture_output=True, timeout=60, check=True,
                         env=child_keyring.environment(os.environ))
    replies = [json.loads(line) for line in run.stdout.splitlines()]
    assert {reply.get("id") for reply in replies if "result" in reply} == {1, 2, 3, 4}
    cards = [reply["params"]["update"] for reply in replies if reply.get("params", {}).get("update", {}).get("sessionUpdate") == "tool_call"]
    assert [card["toolCallId"] for card in cards] == ["memory/e-z0-saved", "memory/e-z0-pending"]
    texts = [reply["params"]["update"]["content"]["text"] for reply in replies
             if reply.get("params", {}).get("update", {}).get("sessionUpdate") == "agent_message_chunk"]
    assert texts[1].startswith("Welcome back.") and texts[-1].startswith("Welcome back.")  # first response and /welcome
    assert all("\u202e" not in card["title"] for card in cards)
    assert log.read_text(encoding="utf-8").count('"direction": "in"') == 4
