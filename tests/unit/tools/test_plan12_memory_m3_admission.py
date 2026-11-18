"""Plan 12.11 Task 3 measurement tool: the parts that run without the released store."""

from __future__ import annotations

import json

import pytest

from optimus.context import memory_extraction as mx
from tools.plan12_memory import m3_admission


def test_without_the_release_nothing_runs(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("P1211_MEMORY_DOCKER_RELEASED", raising=False)
    monkeypatch.setattr(m3_admission, "_provision", lambda *_a: pytest.fail("provisioned without the release"))
    assert m3_admission.main(["--output-dir", "unused"]) == 2
    assert capsys.readouterr().out.startswith("UNRUN")


def test_the_controlled_upstream_answers_from_the_prompt_alone() -> None:
    upstream = m3_admission.Upstream(0.0)
    prompt, _kept = mx.user_prompt([mx.UserBlock("t1:user", "We always run ruff.")], [])
    (candidate,) = json.loads(upstream(prompt=prompt, max_output_tokens=512, purpose=mx.USER_PURPOSE).text)["candidates"]
    assert (candidate["speech_act"], candidate["spans"]) == ("preference", [{"block": "t1:user", "start": 0, "end": 19}])
    correction, _kept = mx.user_prompt([mx.UserBlock("t2:user", "Correction: ruff is optional.")], [mx.ExistingItem("m-" + "a" * 16, "ruff")])
    (retraction,) = json.loads(upstream(prompt=correction, max_output_tokens=512, purpose=mx.USER_PURPOSE).text)["candidates"]
    assert (retraction["speech_act"], retraction["target"]) == ("retraction", "m-" + "a" * 16)
    work = mx.CompletedWork("done", (mx.Evidence("t3:tool:0", "verification"),))
    (lesson,) = json.loads(upstream(prompt=mx.agent_prompt(work), max_output_tokens=512, purpose=mx.AGENT_PURPOSE).text)["candidates"]
    assert lesson["evidence"] == ["t3:tool:0"] and upstream.calls == [mx.USER_PURPOSE, mx.USER_PURPOSE, mx.AGENT_PURPOSE]


def test_compaction_calls_send_nothing_and_are_not_counted() -> None:
    upstream = m3_admission.Upstream(5.0)
    response = upstream(prompt="history", max_output_tokens=300)
    assert response.text is None and [a.outcome for a in response.attempts] == ["not_sent"] and upstream.calls == []


def test_workload_turns_carry_evidence_only_for_task_requests() -> None:
    check = m3_admission._workload_turn({"turn": 7, "kind": "task_request", "text": "Run the tests.", "expected_agent_extraction_call": True})
    edit = m3_admission._workload_turn({"turn": 8, "kind": "task_request", "text": "Rename x.", "expected_agent_extraction_call": False})
    chat = m3_admission._workload_turn({"turn": 9, "kind": "question", "text": "Why?", "expected_agent_extraction_call": False})
    assert check.work is not None and check.work.evidence[0].kind == "verification"
    assert edit.work is not None and edit.work.evidence[0].kind == "edit" and chat.work is None
