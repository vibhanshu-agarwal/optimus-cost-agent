"""#583: a model-authored path or TEST argument holding a control, format, surrogate, unassigned or private-use
character, or a blank filler, or longer than MAX_PATH_CHARS, is rejected at parse time with a fixed message, so it never
reaches the person's text or the model's next-turn history. ZWNJ and ZWJ stay allowed (operator decision).

Every non-ASCII character here is built with chr(): the file itself is ASCII, so no editor or tool can reorder or
convert it."""

from __future__ import annotations

import asyncio
import sys
import unicodedata
from decimal import Decimal
from subprocess import CompletedProcess
from typing import Any

import pytest

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore
from optimus.agent.directives import MAX_PATH_CHARS, AgentDirectiveParseError, parse_agent_plan, unsafe_path_text, windows_path_shape
from optimus.agent.planning_loop import PLANNING_PARSE_FEEDBACK, PlanningTurnKind, PlanningTurnParseError, parse_planning_turn
from optimus.agent.runner import AgentRunner
from optimus.agent.state_store import InMemoryAgentStateStore
from optimus.gateway.models import GatewayResponse, GatewayUsage
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc

ESC, NUL, DEL, CSI, NEL = chr(0x1B), chr(0x00), chr(0x7F), chr(0x9B), chr(0x85)
RLO, LRI, ZWSP, LRM, WJ, BOM, SHY = chr(0x202E), chr(0x2066), chr(0x200B), chr(0x200E), chr(0x2060), chr(0xFEFF), chr(0xAD)
ZWNJ, ZWJ = chr(0x200C), chr(0x200D)
SURROGATE, UNASSIGNED, NONCHAR_FFFE, NONCHAR_FDD0, PRIVATE_USE = chr(0xD800), chr(0x0378), chr(0xFFFE), chr(0xFDD0), chr(0xE000)
FILLERS = {
    "hangul-choseong-filler": chr(0x115F),
    "hangul-jungseong-filler": chr(0x1160),
    "hangul-filler": chr(0x3164),
    "halfwidth-hangul-filler": chr(0xFFA0),
    "braille-blank": chr(0x2800),
}
E_ACUTE, COMBINING_ACUTE, I_DIAERESIS = chr(0xE9), chr(0x0301), chr(0xEF)
NIHONGO = chr(0x65E5) + chr(0x672C) + chr(0x8A9E)
PERSIAN = chr(0x0645) + chr(0x06CC) + ZWNJ + chr(0x062E) + chr(0x0648) + chr(0x0627) + chr(0x0647) + chr(0x0645)
EMOJI_ZWJ = chr(0x1F469) + ZWJ + chr(0x1F4BB)

UNSAFE = {
    "esc": f"src/a{ESC}[31mb.py",
    "nul": f"src/a{NUL}b.py",
    "del": f"src/a{DEL}b.py",
    "c1-csi": f"src/a{CSI}31mb.py",
    "rlo": f"src/a{RLO}yp.exe",
    "lri": f"src/a{LRI}b.py",
    "zwsp": f"src/a{ZWSP}b.py",
    "lrm": f"src/a{LRM}b.py",
    "word-joiner": f"src/a{WJ}b.py",
    "bom": f"src/a{BOM}b.py",
    "soft-hyphen": f"src/a{SHY}b.py",
    "surrogate": f"src/a{SURROGATE}b.py",
    "unassigned": f"src/a{UNASSIGNED}b.py",
    "nonchar-fffe": f"src/a{NONCHAR_FFFE}b.py",
    "nonchar-fdd0": f"src/a{NONCHAR_FDD0}b.py",
    "private-use": f"src/a{PRIVATE_USE}b.py",
    **{name: f"src/a{char}b.py" for name, char in FILLERS.items()},
    "too-long": "a" * (MAX_PATH_CHARS - 2) + ".py",  # exactly MAX_PATH_CHARS + 1
}
ACCEPTED = {
    "latin": f"src/caf{E_ACUTE}.py",
    "nfd-combining-mark": f"src/cafe{COMBINING_ACUTE}.py",
    "cjk": f"docs/{NIHONGO}.md",
    "dots-dashes": f"pkg/na{I_DIAERESIS}ve-file_v1.2.py",
    "zwnj-persian": f"docs/{PERSIAN}.md",
    "zwj-emoji": f"notes/{EMOJI_ZWJ}.txt",
    "at-bound": "a" * (MAX_PATH_CHARS - 3) + ".py",  # exactly MAX_PATH_CHARS
}


def _plan(directive: str, path: str) -> str:
    if directive == "READ":
        return f"READ {path}\n"
    if directive == "WRITE":
        return f"WRITE {path}\ncontent\n"
    return f"EDIT {path}\n<<<<<<< OLD\nold\n======= NEW\nnew\n>>>>>>> END\n"


def _unsafe_characters(text: str) -> list[str]:
    return [hex(ord(c)) for c in text if c not in "\n\r\t" and unicodedata.category(c) in {"Cc", "Cf", "Cs", "Cn", "Co"}]


def test_the_bounds_are_exact():
    assert (len(UNSAFE["too-long"]), len(ACCEPTED["at-bound"])) == (MAX_PATH_CHARS + 1, MAX_PATH_CHARS)


@pytest.mark.parametrize("path", UNSAFE.values(), ids=UNSAFE.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_an_unsafe_path_is_rejected_with_a_fixed_message(directive, path):
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert str(caught.value) == "no valid agent directives"
    # The planner sees no final plan: the turn is unparseable, and its fixed notice quotes nothing.
    with pytest.raises(PlanningTurnParseError) as turn:
        parse_planning_turn(_plan(directive, path))
    assert turn.value.code == "PLAN_PATH_UNSAFE" and path not in str(turn.value)


@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_bulleted_directive_with_an_unsafe_path_is_rejected(directive):
    with pytest.raises(AgentDirectiveParseError, match="^no valid agent directives$"):
        parse_agent_plan("- " + _plan(directive, UNSAFE["esc"]), edit_base="forbidden")


@pytest.mark.parametrize("path", UNSAFE.values(), ids=UNSAFE.keys())
def test_an_unsafe_ranged_read_path_is_rejected_with_a_fixed_message(path):
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"OBSERVE: the header\nREAD: {path}#bytes=0:10\n")

    assert caught.value.code == "READ_PATH_NOT_RELATIVE"
    assert str(caught.value) == "READ path must be workspace-relative"


def test_the_ranged_read_notice_names_the_cause():
    notice = PLANNING_PARSE_FEEDBACK["READ_PATH_NOT_RELATIVE"]
    assert f"at most {MAX_PATH_CHARS} characters" in notice and "no control or invisible format character" in notice


@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_c1_next_line_is_never_a_path(directive):
    """U+0085 is a content separator (#410 R1): its line is not a directive at all, so it is rejected before the path rule."""
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(_plan(directive, f"src/a{NEL}b.py"), edit_base="forbidden")
    assert NEL not in str(caught.value)


@pytest.mark.parametrize("path", ACCEPTED.values(), ids=ACCEPTED.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_legitimate_path_is_still_accepted(directive, path):
    plan = parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert (plan.read_paths[0] if directive == "READ" else plan.write.path) == path


@pytest.mark.parametrize("path", ACCEPTED.values(), ids=ACCEPTED.keys())
def test_a_legitimate_ranged_read_path_is_still_accepted(path):
    ranged = parse_planning_turn(f"OBSERVE: the header\nREAD: {path}#bytes=0:10\n")
    assert ranged.kind is PlanningTurnKind.READ_MORE and ranged.read_requests[0].path == path


def test_the_only_format_characters_a_path_may_hold_are_the_two_joiners():
    formats = (c for c in map(chr, range(sys.maxunicode + 1)) if unicodedata.category(c) == "Cf")
    assert {c for c in formats if not unsafe_path_text(f"a{c}b")} == {ZWNJ, ZWJ}
    assert unsafe_path_text(f"a{ZWNJ}{RLO}b") and unsafe_path_text(f"a{ZWJ}{LRI}b")  # a joiner excuses nothing beside it


UNSAFE_TEST_TOKENS = {
    "c1-csi": f"tests/a{CSI}31mb.py",
    "rlo": f"tests/test_a{RLO}yp.exe",
    "esc": f"tests/a{ESC}b.py",
    "too-long": "a" * (MAX_PATH_CHARS + 1),
    # a TEST argument gets no joiner exemption (the shell guard refuses every format character)
    "zwnj": f"tests/{PERSIAN}.py",
    "zwj": f"tests/{EMOJI_ZWJ}.py",
    # a blank space character other than U+0020 would read as two arguments
    "no-break-space": f"tests/a{chr(0xA0)}b.py",
    "ideographic-space": f"tests/a{chr(0x3000)}b.py",
}


@pytest.mark.parametrize("token", UNSAFE_TEST_TOKENS.values(), ids=UNSAFE_TEST_TOKENS.keys())
def test_an_unsafe_test_argument_is_rejected_at_parse_time_without_quoting_it(token):
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(f"TEST pytest {token}\n", edit_base="forbidden")

    assert str(caught.value) == "unsafe TEST directive"


@pytest.mark.parametrize(
    "command", ["pytest -q tests/unit", "pytest tests/test_a.py::test_x[param]", f"pytest tests/{NIHONGO}.py", "pytest -k smoke -m slow"]
)
def test_a_legitimate_test_command_is_still_accepted(command):
    assert parse_agent_plan(f"TEST {command}\n", edit_base="forbidden").tests == (tuple(command.split()),)


# #590: a colon anywhere (drive, alternate data stream) or a leading backslash (drive-root) in a plan path.
BS, NL = chr(0x5C), chr(0x0A)
WINDOWS_SHAPES = {
    "stream": "a.py:stream",
    "env-stream": ".env:s",
    "drive-relative": "C:rel.py",
    "other-drive": "D:x" + BS + "y.py",
    "data-stream": "a.py::$DATA",
    "env-data-stream": ".env::$DATA",
    "rooted": BS + "rooted.py",
    "rooted-dirs": BS + "Users" + BS + "x.py",
    "sub-stream": "sub/a.py:s",
    # #590: a part Windows reserves: a device name (with or without an extension), a trailing dot (a second name for the
    # same file; "id_rsa." creates id_rsa), or a character no Windows file name may hold.
    "device": "NUL",
    "device-lower": "con",
    "device-in-folder": "sub" + BS + "NUL",
    "device-in-folder-slash": "sub/NUL",
    "device-with-extension": "aux.txt",
    "device-two-extensions": "nul.tar.gz",
    "serial-port": "COM1",
    "serial-port-superscript": "COM" + chr(0xB9),
    "printer-port": "lpt1.x",
    "console-input": "CONIN$",
    "trailing-dot": "a.py.",
    "trailing-dots": "a.py...",
    "trailing-dot-key-file": "id_rsa.",
    "trailing-dot-env": ".env.",
    "trailing-dot-folder": "dir./a.py",
    "three-dots": "a/.../b.py",
    "wildcard": "a*.py",
    "question-mark": "what?.md",
}
ORDINARY = {
    "slash": "sub/a.py",
    "interior-backslash": "sub" + BS + "a.py",
    "dot-folder": "./a.py",
    "dotfile": ".gitignore",
    "inner-dots": "a..b.py",
    "device-prefix": "console.py",
    "device-as-extension": "a.nul",
    "port-zero": "com0",
}


@pytest.mark.parametrize("path", WINDOWS_SHAPES.values(), ids=WINDOWS_SHAPES.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_colon_or_leading_backslash_path_is_rejected_with_a_fixed_message(directive, path):
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert str(caught.value) == "no valid agent directives" and path not in str(caught.value)


@pytest.mark.parametrize("path", WINDOWS_SHAPES.values(), ids=WINDOWS_SHAPES.keys())
def test_a_colon_or_leading_backslash_ranged_read_path_is_rejected_with_a_fixed_message(path):
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"OBSERVE: the header{NL}READ: {path}#bytes=0:10{NL}")

    assert caught.value.code == "READ_PATH_NOT_RELATIVE"
    assert str(caught.value) == "READ path must be workspace-relative" and path not in str(caught.value)


@pytest.mark.parametrize("path", ORDINARY.values(), ids=ORDINARY.keys())
def test_an_ordinary_ranged_read_path_is_still_accepted_after_the_windows_rules(path):
    turn = parse_planning_turn(f"OBSERVE: the header{NL}READ: {path}#bytes=0:10{NL}")

    assert turn.kind is PlanningTurnKind.READ_MORE


@pytest.mark.parametrize("path", ORDINARY.values(), ids=ORDINARY.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_an_ordinary_relative_path_is_still_accepted_after_the_colon_rule(directive, path):
    plan = parse_agent_plan(_plan(directive, path), edit_base="forbidden")

    assert (plan.read_paths[0] if directive == "READ" else plan.write.path) == path


def test_a_pytest_node_id_with_a_double_colon_is_still_a_legitimate_test_argument():
    assert parse_agent_plan(f"TEST pytest tests/test_a.py::test_x{NL}", edit_base="forbidden").tests == (
        ("pytest", "tests/test_a.py::test_x"),
    )


class _SamePlan:
    """Every planning turn returns ``plan``; records what the model was sent."""

    def __init__(self, plan: str) -> None:
        self._plan, self.calls = plan, []

    def create_response(self, *, model: str, input_text: str, metadata: dict[str, Any] | None = None) -> GatewayResponse:
        del model, metadata
        self.calls.append(input_text)
        request_id = f"gw-{len(self.calls)}"
        usage = GatewayUsage(gateway_request_id=request_id, provider="glm", billing_units=1, cost_usd=Decimal("0.001"))
        return GatewayResponse(response_id=request_id, output_text=self._plan, gateway_usage=usage, raw={"id": request_id})


class _RealRunner:
    """The real AgentRunner behind the adapter's runner contract; TEST commands go to a recording shell, never a process."""

    def __init__(self, gateway: _SamePlan) -> None:
        self.commands: list[list[str]] = []
        self._runner = AgentRunner(gateway_client=gateway, model="glm-5.2", state_store=InMemoryAgentStateStore(), shell_runner=self._shell)

    def _shell(self, command: list[str]) -> CompletedProcess[str]:
        self.commands.append(command)
        return CompletedProcess(command, 1, "", "")

    def run(self, request, **kwargs):
        return self._runner.run(request, **kwargs)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list | tuple):
        return [s for item in value for s in _strings(item)]
    return []


async def _drive(tmp_path, gateway):
    """One Agent prompt through the real adapter and the real runner; a permission request, if one comes, is approved."""
    runner = _RealRunner(gateway)
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound
    )
    new = {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    session_id = (await _rpc(adapter, new))["result"]["sessionId"]
    prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": "Change small.py"}]}
    task = asyncio.create_task(_rpc(adapter, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": prompt}))
    permission = asyncio.create_task(outbound.wait_for_request("session/request_permission"))
    await asyncio.wait({task, permission}, timeout=10, return_when=asyncio.FIRST_COMPLETED)
    if permission.done():
        outbound.respond(permission.result()["id"], {"outcome": {"outcome": "selected", "optionId": "approve"}})
    else:
        permission.cancel()
    response = await asyncio.wait_for(task, timeout=10)
    records = adapter._sessions.get(session_id).conversation.records
    return response["result"], outbound, runner, records


E2E = {
    "edit-esc": ("EDIT", UNSAFE["esc"]),
    "edit-nul": ("EDIT", UNSAFE["nul"]),
    "edit-rlo": ("EDIT", UNSAFE["rlo"]),
    "edit-too-long": ("EDIT", UNSAFE["too-long"]),
    "test-c1-csi": ("TEST", UNSAFE_TEST_TOKENS["c1-csi"]),
}


@pytest.mark.parametrize(("directive", "token"), E2E.values(), ids=E2E.keys())
async def test_an_unsafe_token_reaches_neither_the_person_nor_the_history(directive, token, tmp_path):
    """The original symptom: an EDIT path (or a TEST argument) was quoted in the plan entry, the permission request, the
    tool card, the final message and the committed history. Now the plan never parses, the run stops with its fixed
    text, and no text the person or the next turn's model reads carries the token."""
    (tmp_path / "small.py").write_text("old\n")
    gateway = _SamePlan(f"TEST pytest {token}\n" if directive == "TEST" else _plan("EDIT", token))

    result, outbound, runner, records = await _drive(tmp_path, gateway)

    [record] = records.values()
    sent = _strings([n["params"] for n in outbound.notifications]) + _strings(list(outbound.requests))
    committed = _strings([record.completion_text, getattr(record, "plan_text", None)])
    assert [s for s in sent + committed if _unsafe_characters(s) or token in s] == []
    assert len(gateway.calls) > 1 and [call for call in gateway.calls[1:] if token in call] == []
    assert runner.commands == []
    assert result["_meta"]["runStopReason"] == "PLANNING_UNPARSEABLE_RESPONSE"
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    final = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"][-1]
    assert "did not match the required directive grammar" in final


@pytest.mark.parametrize("path", ["id_rsa.", "NUL", "small.py:stream"], ids=["trailing-dot", "device", "stream"])
async def test_a_reserved_windows_name_is_never_written_through_the_real_runner(path, tmp_path):
    """#590: an approved ``WRITE id_rsa.`` created ``id_rsa``, and ``WRITE NUL`` reported a write that was discarded."""
    result, outbound, _runner, _records = await _drive(tmp_path, _SamePlan(_plan("WRITE", path)))

    assert result["_meta"]["runStopReason"] == "PLANNING_UNPARSEABLE_RESPONSE"
    # The loop check-in may ask to continue; no plan approval is asked, so nothing is written.
    assert [r for r in outbound.requests if not r["params"]["_meta"].get("loopCheckIn")] == []
    assert not (tmp_path / "id_rsa").exists()


def test_a_trailing_space_is_reserved_but_directive_padding_is_not_part_of_the_path():
    """A directive line cannot carry a space inside its path token; padding after the token is dropped, as before."""
    assert windows_path_shape("a.py ") and windows_path_shape("dir /a.py")
    assert parse_agent_plan(f"READ a.py {NL}", edit_base="forbidden").read_paths == ("a.py",)
    with pytest.raises(PlanningTurnParseError):
        parse_planning_turn(f"OBSERVE: the header{NL}READ: a.py #bytes=0:10{NL}")


# #590: a positional TEST argument names a file (the part before a node id's ::), so it follows the plan path rule.
WINDOWS_TEST_ARGUMENTS = {
    "stream": "a.py:stream",
    "stream-with-node-id": "a.py:s::test_x",
    "drive-relative": "C:rel.py",
    "rooted": BS + "rooted.py",
    "device": "NUL",
    "device-in-folder": "tests/aux.py",
    "trailing-dot": "tests/test_a.py.",
    "quoted-rooted": chr(0x22) + BS + "rooted.py" + chr(0x22),
    "option-value": "--debug=NUL",
    "option-value-stream": "--junitxml=out.xml:stream",
    "option-value-is-not-a-node-id": "--junitxml=out.xml::report",
    "quoted-file": chr(0x22) + "tests/test_a.py" + chr(0x22),
    "quoted-option-value": "--junitxml=" + chr(0x22) + "out.xml" + chr(0x22),
    "grouped-config": "-qc NUL",
    "config-path": "-c " + BS + "rooted.ini",
    "long-option-path": "--rootdir aux",
    "after-separator": "-- -sample.py.",
    "separator-then-option": "-- -k NUL",
    "response-file": "@args.txt",
}


@pytest.mark.parametrize("argument", WINDOWS_TEST_ARGUMENTS.values(), ids=WINDOWS_TEST_ARGUMENTS.keys())
@pytest.mark.parametrize("prefix", ["pytest", "pytest -q", "pytest --tb=short tests"], ids=["first", "after-flag", "after-path"])
def test_a_windows_shaped_test_argument_is_rejected_at_parse_time_without_quoting_it(prefix, argument):
    with pytest.raises(AgentDirectiveParseError) as caught:
        parse_agent_plan(f"TEST {prefix} {argument}{NL}", edit_base="forbidden")

    assert str(caught.value) == "unsafe TEST directive"


@pytest.mark.parametrize(
    "command",
    [
        "pytest -p no:cacheprovider tests/test_a.py::test_x[a:b]",
        "pytest -k smoke:fast -m slow tests",
        "pytest --cov-report=xml:cov.xml --deselect=tests/test_a.py::test_x .",
        "pytest --cov-report xml:cov.xml --deselect tests/test_a.py::test_x[a:b] -n 2 tests",
        "pytest --log-date-format=%H:%M:%S --ignore-glob=tests/*_slow.py tests",
        "pytest --log-date-format %H:%M:%S -- tests/test_a.py",
        "pytest -o cache_dir=x -W error::UserWarning -c pytest.ini tests/unit",
    ],
)
def test_an_option_value_may_hold_a_colon(command):
    assert parse_agent_plan(f"TEST {command}{NL}", edit_base="forbidden").tests == (tuple(command.split()),)


# --- What #588 left open on #583: the REFUSE reason, and a notice that names the cause -----------------------------

REFUSE_UNSAFE = {key: UNSAFE[key] for key in ("esc", "nul", "c1-csi", "rlo", "lri", "zwsp", "private-use")}


@pytest.mark.parametrize("token", REFUSE_UNSAFE.values(), ids=REFUSE_UNSAFE.keys())
def test_an_unsafe_refuse_reason_is_rejected_with_a_fixed_message(token):
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"REFUSE: I will not change {token}\n")

    assert caught.value.code == "REFUSE_UNSAFE_TEXT" and token not in str(caught.value)


def test_a_lone_surrogate_in_a_refuse_reason_is_refused_not_a_crash():
    """Codex review: a JSON reply can decode to one; the 512-byte check raised UnicodeEncodeError before the rule."""
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"REFUSE: I will not change {chr(0xD800)}\n")

    assert caught.value.code == "REFUSE_UNSAFE_TEXT"


@pytest.mark.parametrize("reason", [f"I will not change docs/{PERSIAN}.md", f"caf{E_ACUTE} {NIHONGO} {EMOJI_ZWJ}"], ids=["zwnj", "letters-emoji"])
def test_a_refuse_reason_in_any_script_is_still_accepted(reason):
    assert parse_planning_turn(f"REFUSE: {reason}\n").reason == reason


def test_an_over_long_refuse_reason_was_already_rejected_by_its_byte_cap():
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"REFUSE: {UNSAFE['too-long']}\n")

    assert caught.value.code == "REFUSE_TOO_LONG"


@pytest.mark.parametrize("path", [*UNSAFE.values(), *WINDOWS_SHAPES.values()], ids=[*UNSAFE, *(f"windows-{k}" for k in WINDOWS_SHAPES)])
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT"])
def test_a_final_plan_path_rejection_gets_a_notice_that_names_the_cause(directive, path):
    """#583 / #590: the generic grammar notice made a model that cannot see the character repeat the same reply."""
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(_plan(directive, path))

    assert caught.value.code == "PLAN_PATH_UNSAFE" and path not in str(caught.value)


def test_a_reply_that_is_no_plan_still_gets_the_grammar_notice():
    with pytest.raises(PlanningTurnParseError) as caught:
        parse_planning_turn(f"Here is prose about src/a{ESC}b.py\n")

    assert caught.value.code == "GRAMMAR_UNRECOGNIZED"


@pytest.mark.parametrize("code", ["PLAN_PATH_UNSAFE", "READ_PATH_NOT_RELATIVE"])
def test_both_path_notices_name_every_cause(code):
    notice = PLANNING_PARSE_FEEDBACK[code]
    for cause in (f"at most {MAX_PATH_CHARS} characters", "control or invisible format character", "colon", "leading backslash", "reserved Windows name"):
        assert cause in notice, cause


def test_the_refuse_notice_names_the_cause():
    assert "control or invisible format characters" in PLANNING_PARSE_FEEDBACK["REFUSE_UNSAFE_TEXT"]


@pytest.mark.parametrize("token", [UNSAFE[key] for key in ("esc", "nul", "rlo", "too-long")], ids=["esc", "nul", "rlo", "too-long"])
async def test_an_unsafe_refuse_reason_reaches_neither_the_person_nor_the_history(token, tmp_path):
    """The REFUSE reason was the run's output: shown in two plan updates, the final message and the committed history."""
    gateway = _SamePlan(f"REFUSE: I will not change {token}\n")

    result, outbound, runner, records = await _drive(tmp_path, gateway)

    [record] = records.values()
    sent = _strings([n["params"] for n in outbound.notifications]) + _strings(list(outbound.requests))
    committed = _strings([record.completion_text, getattr(record, "plan_text", None)])
    assert [s for s in sent + committed if _unsafe_characters(s) or token in s] == []
    assert len(gateway.calls) > 1 and [call for call in gateway.calls[1:] if token in call] == []
    code = "REFUSE_TOO_LONG" if token == UNSAFE["too-long"] else "REFUSE_UNSAFE_TEXT"
    assert PLANNING_PARSE_FEEDBACK[code] in gateway.calls[1]
    assert result["_meta"]["runStopReason"] == "PLANNING_UNPARSEABLE_RESPONSE"


@pytest.mark.parametrize("token", [UNSAFE[key] for key in ("esc", "nul", "rlo", "too-long")], ids=["esc", "nul", "rlo", "too-long"])
async def test_the_next_planning_call_names_why_a_final_plan_path_was_refused(token, tmp_path):
    (tmp_path / "small.py").write_text("old\n")
    gateway = _SamePlan(_plan("EDIT", token))

    await _drive(tmp_path, gateway)

    assert PLANNING_PARSE_FEEDBACK["PLAN_PATH_UNSAFE"] in gateway.calls[1]
