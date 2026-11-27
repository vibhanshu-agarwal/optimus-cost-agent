"""#591: a path or TEST argument the model writes as Markdown (a link, an image, a bare address) is shown inert.

Sentences the agent authors (the EDIT failure, the tool cards, the "Tool activity:" and "Completed:" lists, the TEST-stopped
and WRITE-refused texts) escape it where they are shown; the run result, the committed history and memory extraction keep the
raw text. Plan entries and the permission request show the model's own text in a fenced code block, so the person approves
exactly what the model wrote; the plan hash and the applied content are unchanged. Inertness is checked with a CommonMark
parser (markdown-it-py); Zed's own rendering, including whether it auto-links a bare address inside a code block, is not
verified here. Backticks are built with chr(96)."""

from __future__ import annotations

import asyncio
import hashlib

import pytest
from markdown_it import MarkdownIt

from optimus.acp import spec
from optimus.acp.shapes import code_block
from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, RecordingOutboundChannel, _completion_message
from optimus.agent.edits import edit_failure_text
from optimus.agent.models import AgentRunResult, AgentRunStatus, AgentToolCall, ExecutionMode
from optimus.context.memory_extraction import evidence_from
from tests.unit.agent import test_directive_path_characters as harness
from tests.unit.agent.test_directive_path_characters import _drive, _plan, _SamePlan, _strings

LBR, RBR, LPAR, RPAR, BANG, TICK, BS = chr(0x5B), chr(0x5D), chr(0x28), chr(0x29), chr(0x21), chr(96), chr(0x5C)
TOKENS = {
    "link": f"{LBR}README.md{RBR}{LPAR}//evil.example/x{RPAR}",
    "image": f"{BANG}{LBR}x{RBR}{LPAR}//evil.example/y{RPAR}",
    "bare-address": "www.evil.example/x",
}
# A colon in a plan path or a TEST file argument is refused at parse time (#583, #590): none of these reaches a surface.
REFUSED = {
    "https-link": f"{LBR}README.md{RBR}{LPAR}https://evil.example/x{RPAR}",
    "https-image": f"{BANG}{LBR}x{RBR}{LPAR}https://evil.example/y{RPAR}",
    "bare-https": "https://evil.example/x",
}
MD = MarkdownIt("commonmark")


def _live(text: str) -> list[str]:
    """What a CommonMark client would render as a link or an image, or a bare address it might auto-link, outside code blocks."""
    found = []
    for token in MD.parse(text):
        for child in token.children or ():
            if child.type in ("link_open", "image"):
                found.append(child.type)
            elif child.type == "text" and ("www." in child.content or "://" in child.content):
                found.append(child.content)
    return found


def _fenced(text: str) -> str | None:
    """The content of `text` when it is exactly one fenced code block, else None."""
    tokens = MD.parse(text)
    return tokens[0].content if len(tokens) == 1 and tokens[0].type == "fence" else None


def _target(tmp_path, directive: str, token: str) -> None:
    if directive in ("READ", "WRITE", "EDIT"):  # EDIT: a file that exists, so the run reaches the edit and fails on its OLD text
        (tmp_path / token).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / token).write_text("other\n")


def _plan_for(directive: str, token: str) -> str:
    return f"TEST pytest {token}\n" if directive == "TEST" else _plan("EDIT" if directive == "EDIT-unseen" else directive, token)


@pytest.mark.parametrize("token", TOKENS.values(), ids=TOKENS.keys())
@pytest.mark.parametrize("directive", ["READ", "WRITE", "EDIT", "EDIT-unseen", "TEST"])
async def test_a_markdown_token_is_inert_everywhere_the_person_reads_it(directive, token, tmp_path):
    _target(tmp_path, directive, token)
    plan = _plan_for(directive, token)

    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan(plan))

    assert "_meta" in result
    sent = _strings([n["params"] for n in outbound.notifications]) + _strings(list(outbound.requests))
    assert [(text, _live(text)) for text in sent if _live(text)] == []
    updates = [n["params"]["update"] for n in outbound.notifications if n["method"] == "session/update"]
    entries = [entry["content"] for u in updates if u["sessionUpdate"] == "plan" for entry in u["entries"]]
    assert all(_fenced(entry) is not None for entry in entries)
    for request in outbound.requests:  # the approval shows, in one code block, exactly the bytes the plan hash covers
        if request["method"] == "session/request_permission" and not request["params"]["_meta"].get("loopCheckIn"):
            [content] = request["params"]["toolCall"]["content"]
            approved = _fenced(content["content"]["text"])
            assert approved is not None and approved.startswith(plan.split(chr(10))[0])
            assert hashlib.sha256(approved.encode("utf-8")).hexdigest() == request["params"]["options"][0]["metadata"]["planHash"]
    # The committed history keeps the raw text: the next turn's model reads what ran, not escaped Markdown.
    [record] = records.values()
    assert BS not in record.completion_text and any(m in record.completion_text for m in (f"{RBR}{LPAR}", f"{BANG}{LBR}", "www."))


@pytest.mark.parametrize("token", REFUSED.values(), ids=REFUSED.keys())
@pytest.mark.parametrize("directive", ["WRITE", "EDIT-unseen", "TEST"])
async def test_an_https_token_never_reaches_a_surface(directive, token, tmp_path):
    result, outbound, _runner, records = await _drive(tmp_path, _SamePlan(_plan_for(directive, token)))

    assert result["_meta"]["runStopReason"] == "PLANNING_UNPARSEABLE_RESPONSE"
    sent = _strings([n["params"] for n in outbound.notifications]) + _strings(list(outbound.requests))
    committed = _strings([[r.completion_text, getattr(r, "plan_text", None)] for r in records.values()])
    assert [text for text in sent + committed if "evil.example" in text] == []


async def test_memory_extraction_still_parses_the_raw_read_summary(tmp_path, monkeypatch):
    """`evidence_from` reads "read <path>" from the run's tool calls; escaping happens only where a card or message is shown."""
    path = f"{LBR}a{RBR}{LPAR}//e.example/x{RPAR}/README.md"
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("hello\n")
    results = []
    real_run = harness._RealRunner.run

    def run(self, request, **kwargs):
        results.append(real_run(self, request, **kwargs))
        return results[-1]

    monkeypatch.setattr(harness._RealRunner, "run", run)

    _result, outbound, _runner, _records = await _drive(tmp_path, _SamePlan(f"READ {path}\n"))

    shown = (tmp_path / path).relative_to(tmp_path).as_posix()  # the reader reports the resolved relative path
    calls = [call for result in results for call in result.tool_calls if call.tool_name == "file_reader"]
    assert calls and {call.summary for call in calls} == {f"read {shown}"}  # the planning read and the approved READ
    assert {item.kind for item in evidence_from("run", calls)} == {"document"}
    cards = [u["content"][0]["content"]["text"] for n in outbound.notifications if (u := n["params"]["update"])["sessionUpdate"] == "tool_call"]
    assert f"read {shown}" not in cards and _live(cards[-1]) == [] and BS in cards[-1]


def _result(stop_reason: str | None, output_text: str, calls: tuple[AgentToolCall, ...] = (), mutations: int = 0) -> AgentRunResult:
    return AgentRunResult(
        run_id="r", session_id="s", execution_mode=ExecutionMode.AGENT, status=AgentRunStatus.FAILED if stop_reason else AgentRunStatus.COMPLETED, final_state="X",
        output_text=output_text, tool_calls=calls, total_cost_usd=0, stop_reason=stop_reason, mutation_count=mutations)


@pytest.mark.parametrize("token", TOKENS.values(), ids=TOKENS.keys())
def test_only_the_token_is_escaped_and_the_history_text_is_rebuilt_unchanged(token):
    """The EDIT failure, and two agent-authored texts the first sweep did not list: a stopped TEST's "Applied:" list and a
    refused WRITE's sentence. Only the token is escaped; the identity rebuilds each text byte for byte."""
    wrote = AgentToolCall(tool_name="write_file", summary=f"wrote {token}", authorization_outcome="ALLOW")
    stopped = _result("TEST_TIMED_OUT", f"A TEST directive timed out; the later directives were not run. Applied:{chr(10)}- wrote {token}", calls=(wrote,))
    refused = _result("WRITE_LINE_ENDINGS_MIXED", f"{token} has mixed line endings, which Optimus does not rewrite. This WRITE did not change the file.")
    failed = _result("EDIT_NOT_APPLICABLE", edit_failure_text("EDIT_OLD_NOT_FOUND", token))
    for result in (stopped, refused, failed):
        shown = _completion_message(result, spec._shown)
        assert _live(shown) == [] and _completion_message(result) == result.output_text
        assert shown == result.output_text.replace(token, spec._shown(token))
    assert _completion_message(failed, spec._shown).endswith("(EDIT_OLD_NOT_FOUND)")  # the closed code ends it (#574)


async def test_an_index_tool_card_escapes_the_model_query():
    outbound = RecordingOutboundChannel()
    adapter = AcpDuplexAdapter(runner=None, workspace_root=".", sessions=InMemoryAcpSpecSessionStore(), outbound=outbound)
    card = adapter._index_tool_cards("s", asyncio.get_running_loop())
    query = f"{TOKENS['link']} https://evil.example/q"

    card("c1", "started", "SEARCH", query, "")
    card("c1", "completed", "SEARCH", query, f"SEARCH {query}: 3 lines in 2 ms")
    for _ in range(5):
        await asyncio.sleep(0)

    texts = _strings([n["params"] for n in outbound.notifications])
    assert len(outbound.notifications) == 2 and [(t, _live(t)) for t in texts if _live(t)] == []


FENCE3, FENCE4 = TICK * 3, TICK * 4
HOSTILE = {
    "triple-fence": f"WRITE a.md{chr(10)}{FENCE3}{chr(10)}{LBR}x{RBR}{LPAR}//evil.example/x{RPAR}{chr(10)}{FENCE3}{chr(10)}",
    "longer-fence": f"WRITE a.md{chr(10)}{FENCE4}python{chr(10)}x{chr(10)}{FENCE4}{chr(10)}{BANG}{LBR}i{RBR}{LPAR}//e/y{RPAR}{chr(10)}",
    "indented-fence": f"WRITE a.md{chr(10)}   {FENCE3}{chr(10)}www.evil.example{chr(10)}",
    "inline-ticks": f"READ a{TICK}b{TICK * 2}c.py{chr(10)}",
    "no-final-newline": f"READ a.py{chr(10)}{FENCE3}",
    "crlf": f"WRITE a.md{chr(13)}{chr(10)}{FENCE3}{chr(13)}{chr(10)}x{chr(13)}{chr(10)}",
    "tilde-fence": f"WRITE a.md{chr(10)}~~~{chr(10)}x{chr(10)}",
}


@pytest.mark.parametrize("text", HOSTILE.values(), ids=HOSTILE.keys())
def test_no_content_breaks_out_of_its_code_block(text):
    shown = code_block(text)

    assert _fenced(shown) == (text if text.endswith((chr(10), chr(13))) else text + chr(10)).replace(chr(13) + chr(10), chr(10))
    assert shown.startswith(FENCE3)


async def test_a_fenced_plan_keeps_its_hash_and_its_applied_content(tmp_path):
    body = f"intro{chr(10)}{FENCE3}{chr(10)}{LBR}x{RBR}{LPAR}//evil.example/x{RPAR}{chr(10)}{FENCE4}{chr(10)}"
    (tmp_path / "a.md").write_text("old\n")
    plan = f"WRITE a.md{chr(10)}{body}"

    result, outbound, _runner, _records = await _drive(tmp_path, _SamePlan(plan))

    [request] = [r for r in outbound.requests if r["method"] == "session/request_permission" and not r["params"]["_meta"].get("loopCheckIn")]
    assert request["params"]["options"][0]["metadata"]["planHash"] == hashlib.sha256(plan.encode("utf-8")).hexdigest()
    assert _fenced(request["params"]["toolCall"]["content"][0]["content"]["text"]) == plan
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == body
    assert "_meta" in result


# --- Codex review round 1 (#591) ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("token", TOKENS.values(), ids=TOKENS.keys())
async def test_a_recovery_check_in_and_its_stop_text_show_the_repeated_step_inert(token, tmp_path):
    """The check-in quotes the repeated step (a model-authored ranged READ path); so does the stop text after Stop."""
    from tests.unit.acp.test_loop_checkin import STOP, _messages, _next_request, _start

    path = f"{token}/b.py"  # not a.py: the prompt names a.py, and two would be ambiguous
    (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / path).write_text("0123456789abcdef", encoding="utf-8")
    _adapter, _gateway, outbound, session_id, prompt = await _start(tmp_path, [f"OBSERVE: need the header{chr(10)}READ: {path}#bytes=0:5{chr(10)}"] * 4)
    checkin = await asyncio.wait_for(_next_request(outbound, 0), 15)
    checkin_text = checkin["params"]["toolCall"]["content"][0]["content"]["text"]
    outbound.respond(checkin["id"], STOP)
    await prompt

    assert "repeated the read of" in checkin_text and _live(checkin_text) == []
    shown = _messages(outbound)
    assert "Last repeated step: " in shown and _live(shown) == []
    [record] = _adapter._sessions.get(session_id).conversation.records.values()
    assert BS not in record.completion_text and "Last repeated step: " in record.completion_text  # the history keeps the raw step


def test_a_stopped_test_rebuilds_its_applied_list_from_the_write_calls():
    """A resolved write summary can hold a line break (a POSIX symlink target); every part of it is shown escaped."""
    summary = f"wrote a{chr(10)}{TOKENS['link']}"
    text = f"A TEST directive timed out; the later directives were not run. Applied:{chr(10)}- {summary}"
    result = _result("TEST_TIMED_OUT", text, calls=(AgentToolCall(tool_name="write_file", summary=summary, authorization_outcome="ALLOW"),))

    assert _live(_completion_message(result, spec._shown)) == [] and _completion_message(result) == text


def test_a_shown_token_is_never_shortened():
    """A long TEST command keeps its exit code in view: the shown text is escaped, never cut."""
    summary = "ran pytest " + " ".join(f"tests/test_{n}.py" for n in range(400)) + " exit=1"
    assert spec._shown(summary).endswith("exit=1")


def test_the_live_verifier_reads_the_plan_lines_inside_their_code_blocks():
    from optimus.acp.e2e_transcript import E2eAcpTranscriptWriter
    from optimus.acp.operator_verify import latest_plan_text_from_transcript
    from optimus.acp.shapes import build_plan_session_update, code_block_content

    plan = f"WRITE a.md{chr(10)}x {FENCE3} y{chr(10)}TEST pytest -q{chr(10)}"
    transcript = E2eAcpTranscriptWriter()
    transcript.record_inbound({"method": "session/update", "params": build_plan_session_update(session_id="s", plan_text=plan)})

    assert latest_plan_text_from_transcript(transcript) == plan.strip()
    assert code_block_content("not fenced") == "not fenced" and code_block_content(code_block(FENCE4)) == FENCE4


def test_a_host_line_escapes_only_what_it_quotes_and_everything_when_a_part_is_missing():
    link = TOKENS["link"]
    line = f"Planning paused: the model repeated the read of {link}#bytes=0:5. Stop ends this turn."

    shown = spec._shown_quoting(line, (f"{link}#bytes=0:5",))
    assert _live(shown) == [] and shown.endswith("Stop ends this turn.")  # the fixed text is left as it was
    assert _live(spec._shown_quoting(line, ("not in the line",))) == []  # a part not found: the whole line is escaped
