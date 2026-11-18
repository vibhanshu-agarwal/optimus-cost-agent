"""Plan 12.11 Task 4: compaction extraction. Turns a summary covers are extracted from their raw user text, never the summary, in
the turn's one user slot; text already decided is not extracted again; what cannot be extracted is an explicit gap; D9 holds."""

from __future__ import annotations

import json

from optimus.acp import memory_commands as mc
from optimus.context import memory_extraction as mx
from tests.unit.context.test_memory_extractor import _completed, _harness, _until, _Upstream

SCOPE = "project"
RULE = "From now on, new tests should use plain pytest asserts."
COVERED = mx.UserBlock("turn:abc:1:user", RULE)
PROPOSAL = json.dumps({"candidates": [{"speech_act": "preference", "kind": "preference", "title": "test style",
                                       "statement": RULE, "spans": [{"block": COVERED.block, "start": 0, "end": len(RULE)}]}]})
LESSON = json.dumps({"candidates": [{"speech_act": "assertion", "kind": "lesson", "title": "fake clock",
                                     "statement": "The scheduler test needs a fake clock.", "evidence": ["ev-1"]}]})


def _turn(n: int, text: str, work: mx.CompletedWork | None = None) -> mx.TurnInput:
    return mx.TurnInput(f"s:{n}", SCOPE, (mx.UserBlock(f"s:{n}:user", text),), work, (), True)


def test_covered_raw_text_is_extracted_in_the_user_slot_and_d9_keeps_it_off() -> None:
    upstream = _Upstream(_completed(PROPOSAL), _completed(LESSON, 2))
    extractor, _settlement, outcomes, receipts = _harness(upstream)
    assert extractor.covered((COVERED,), SCOPE) == 1
    work = mx.CompletedWork("done", (mx.Evidence("ev-1", "verification"),))
    extractor.submit(_turn(2, "Please refactor the payment module into two services now.", work))
    _until(outcomes, 2)
    extractor.close()
    purposes = sorted(purpose for _turn_id, purpose, _tokens, _prompt in upstream.calls)
    assert purposes == [mx.COMPACTION_PURPOSE, mx.AGENT_PURPOSE]  # one user-slot call and the agent's: never a third
    (prompt,) = [p for _t, purpose, _k, p in upstream.calls if purpose == mx.COMPACTION_PURPOSE]
    assert RULE in prompt and "payment module" in prompt  # the covered raw text and this turn's own, together
    compaction = next(o for o in outcomes if o.purpose == mx.COMPACTION_PURPOSE)
    assert compaction.reasons == ("USER_AUTOMATIC_OFF",) and [n.action for n in compaction.notices] == ["off"]
    assert {r.purpose for r in receipts} == {mx.COMPACTION_PURPOSE, mx.AGENT_PURPOSE}  # receipts carry the purpose
    # the covered source is held, so the user can switch it on explicitly (D10)
    (off,) = compaction.notices
    commands = mc.MemoryCommands(extractor.store, trusted=True, sanitize=lambda v: v, scope=SCOPE, keyed=extractor.keyed,
                                 source=extractor.source, source_digest=extractor.source_digest)
    answer = commands.run(mc.MemoryCommand("switch_on", item=off.item, version=1), block="command:1")
    assert answer.notices and answer.notices[0][0].saved


def test_text_already_decided_or_skipped_is_never_queued_again() -> None:
    upstream = _Upstream(_completed(json.dumps({"candidates": []})))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor.submit(mx.TurnInput("s:1", SCOPE, (mx.UserBlock("s:1:user", RULE),), None, (), True))
    _until(outcomes, 1)
    assert extractor.covered((mx.UserBlock("turn:abc:1:user", RULE),), SCOPE) == 0  # the user job already decided it
    assert extractor.covered((mx.UserBlock("turn:abc:2:user", "Is it green yet?"),), SCOPE) == 0  # the prefilter skips it
    assert extractor.covered((mx.UserBlock("turn:abc:3:user", "Never deploy on a Friday afternoon."),) * 2, SCOPE) == 1
    extractor.close()


def test_a_failed_user_job_leaves_its_text_for_compaction_to_catch_up() -> None:
    upstream = _Upstream(_completed("not json"), _completed(json.dumps({"candidates": []}), 2))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    extractor.submit(mx.TurnInput("s:1", SCOPE, (mx.UserBlock("s:1:user", RULE),), None, (), True))
    _until(outcomes, 1)
    assert outcomes[0].incomplete is not None
    assert extractor.covered((mx.UserBlock("turn:abc:1:user", RULE),), SCOPE) == 1
    extractor.close()


def test_covered_text_over_the_input_cap_is_an_explicit_gap() -> None:
    upstream = _Upstream(_completed(json.dumps({"candidates": []})))
    extractor, _settlement, outcomes, _receipts = _harness(upstream)
    huge = mx.UserBlock("turn:abc:9:user", "Always keep this rule in mind " + "word " * 9000)
    small = mx.UserBlock("turn:abc:10:user", "Never deploy on a Friday afternoon.")
    assert extractor.covered((huge, small), SCOPE) == 2
    extractor.submit(_turn(11, "ok"))
    _until(outcomes, 1)
    extractor.close()
    (outcome,) = outcomes
    assert outcome.purpose == mx.COMPACTION_PURPOSE and outcome.gaps == ("turn:abc:9:user:over_input_cap",)
    assert extractor.covered((huge,), SCOPE) == 1  # a gap stays undecided, so a later compaction may try it again
