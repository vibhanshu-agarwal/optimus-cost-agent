"""#688: a workspace file or folder name written as Markdown (a link, an image, a bare address) is inert in the sentence that
lists it. The ambiguous-reference, not-readable and too-large stops are escaped where they are shown (#591's `_shown`); the run
result and the committed history keep the raw text, so the next turn's selection reads the names as they are on disk.
Inertness is checked with the CommonMark parser #591's tests use. Zed's own rendering is not verified here."""

from __future__ import annotations

import asyncio

import pytest

from optimus.acp.spec import AcpDuplexAdapter, InMemoryAcpSpecSessionStore, _completion_message, _shown
from optimus.agent.models import AgentRunResult, AgentRunStatus, ExecutionMode
from tests.support.contract_doubles import checked_agent_runner
from tests.unit.acp.test_markdown_path_display import TOKENS, _live
from tests.unit.acp.test_spec_protocol import _recording_outbound, _rpc
from tests.unit.agent.test_directive_path_characters import _RealRunner, _SamePlan, _strings


async def _prompt(tmp_path, text: str, mode: str):
    runner = _RealRunner(_SamePlan("WRITE a.py\nx\n"))
    outbound = _recording_outbound()
    adapter = AcpDuplexAdapter(
        runner=checked_agent_runner(runner), workspace_root=tmp_path, sessions=InMemoryAcpSpecSessionStore(), outbound=outbound
    )
    new = {"jsonrpc": "2.0", "id": 1, "method": "session/new", "params": {"cwd": str(tmp_path), "mcpServers": []}}
    session_id = (await _rpc(adapter, new))["result"]["sessionId"]
    set_mode = {"jsonrpc": "2.0", "id": "m", "method": "session/set_mode", "params": {"sessionId": session_id, "modeId": mode}}
    assert "result" in await _rpc(adapter, set_mode)
    prompt = {"sessionId": session_id, "prompt": [{"type": "text", "text": text}]}
    response = await asyncio.wait_for(_rpc(adapter, {"jsonrpc": "2.0", "id": 2, "method": "session/prompt", "params": prompt}), timeout=10)
    return response["result"], outbound, adapter._sessions.get(session_id).conversation.records


@pytest.mark.parametrize("mode", ["agent", "chat"])
@pytest.mark.parametrize("token", TOKENS.values(), ids=TOKENS.keys())
async def test_an_ambiguous_candidate_named_as_markdown_is_inert_where_it_is_shown(token, mode, tmp_path):
    (tmp_path / "a.py").write_text("one\n")
    (tmp_path / token).mkdir(parents=True)
    (tmp_path / token / "a.py").write_text("two\n")

    result, outbound, records = await _prompt(tmp_path, "Update a.py", mode)

    assert result["_meta"]["runStopReason"] == "AMBIGUOUS_WORKSPACE_REFERENCE"
    sent = _strings([n["params"] for n in outbound.notifications]) + _strings(list(outbound.requests))
    assert any("is ambiguous" in text for text in sent)
    assert [(text, _live(text)) for text in sent if _live(text)] == []
    [record] = records.values()  # the committed history keeps the name exactly as it is on disk
    on_disk = (tmp_path / token / "a.py").relative_to(tmp_path).as_posix()
    assert on_disk in record.completion_text and "\\" not in record.completion_text


def _stop(code: str, text: str) -> AgentRunResult:
    return AgentRunResult(
        run_id="r",
        session_id="s",
        execution_mode=ExecutionMode.AGENT,
        status=AgentRunStatus.FAILED,
        final_state="FAILED",
        output_text=text,
        stop_reason=code,
    )


@pytest.mark.parametrize("token", TOKENS.values(), ids=TOKENS.keys())
@pytest.mark.parametrize(
    ("code", "text"),
    [
        (
            "AMBIGUOUS_WORKSPACE_REFERENCE",
            "Workspace reference 'a.py' is ambiguous. Candidates, most likely first: {t}/a.py (named in this session); a.py. The order is a suggestion and chose nothing. Retry with one exact workspace-relative path.",
        ),
        ("WORKSPACE_REFERENCE_NOT_READABLE", "Workspace reference '{t}/a.py' cannot be read safely: it is a link."),
        (
            "REQUIRED_WORKSPACE_FILE_TOO_LARGE",
            "Workspace reference '{t}/a.py' exceeds the available context budget. Retry with a smaller scope.",
        ),
    ],
    ids=["ranked-ambiguity", "not-readable", "too-large"],
)
def test_every_workspace_context_stop_is_shown_inert_and_kept_raw(code, text, token):
    result = _stop(code, text.format(t=token))

    assert _live(_completion_message(result, _shown)) == []
    assert _completion_message(result) == result.output_text
