"""Plan 12.11 Task 4: what memory a turn is served and where it sits in the prompt (design spec v4 §5; ADR-039, ADR-041)."""

from __future__ import annotations

from context_engine.memory_contracts import ServedMemory
from optimus.agent import prompts
from optimus.context import memory_serving as ms


def _item(n: int, trust: str = "user-authored", kind: str = "constraint", version: int = 1, statement: str = "") -> ServedMemory:
    return ServedMemory("p-1", f"m-{n:016x}", version, trust, kind, "project", f"title {n}", statement or f"Rule number {n}.", ())


def test_user_items_are_protected_and_agent_lessons_are_optional_and_bounded() -> None:
    items = [_item(9, "agent-derived", "episode"), _item(1, kind="fact"), _item(8, "agent-derived", "lesson"),
             _item(2, kind="constraint"), *[_item(20 + n, "agent-derived", "lesson") for n in range(4)]]
    served = ms.select(items)
    assert [i.item for i in served.protected] == [_item(2).item, _item(1).item]  # constraints first, every user item kept
    assert [i.kind for i in served.optional] == ["lesson", "lesson", "lesson"]  # ranked, at most three
    assert served.omitted_optional == 3
    assert ms.select(list(reversed(items))) == served  # input order never decides


def test_nothing_served_renders_nothing_so_the_prompt_is_unchanged() -> None:
    assert ms.render(ms.EMPTY) == ""
    assert "partial" in ms.render(ms.ServedSet((), (), complete=False))


def test_the_block_cites_each_item_and_states_what_was_left_out() -> None:
    block = ms.render(ms.select([_item(1, statement="Never push to main."), *[_item(30 + n, "agent-derived", "lesson") for n in range(5)]]))
    assert "- [memory:m-0000000000000001@1] (the user's constraint) Never push to main." in block
    assert "(2 optional agent lessons were left out)" in block and block.endswith(ms.FOOTER + "\n")


def test_the_block_is_sanitized_and_kept_to_one_line_per_item() -> None:
    block = ms.render(ms.select([_item(1, statement="Use token sk-secret\tnow.")]), sanitize=lambda s: s.replace("sk-secret", "[REDACTED]"))
    assert "sk-secret" not in block and "[REDACTED] now." in block


def test_only_what_was_served_can_be_cited() -> None:
    served = ms.select([_item(1, version=3), _item(2, "agent-derived", "lesson")])
    report = ms.check_citations("Per [memory:m-0000000000000001@3] and [memory:m-0000000000000002@1], also "
                                "[memory:m-0000000000000001@2] and [memory:m-00000000000000ff@1].", served)
    assert report.cited == ((_item(1).item, 3), (_item(2).item, 1))
    assert report.obsolete == ((_item(1).item, 2, 3),) and report.invented == ("m-00000000000000ff",)
    assert ms.citation_note(report) is not None and ms.citation_note(ms.check_citations("[memory:m-0000000000000001@3]", served)) is None


def test_memory_binds_the_plan_context_digest_and_none_leaves_it_alone() -> None:
    digest = "a" * 64
    assert ms.bind_digest(digest, "") == digest
    bound = ms.bind_digest(digest, "block")
    assert bound != digest and bound != ms.bind_digest(digest, "block2") and len(bound) == 64


def _chat(memory_context: str, *, indexed: bool) -> str:
    if indexed:
        return prompts.build_indexed_chat_input("Q?", workspace_context="", conversation_envelope="history", repo_map="map",
                                                index_results="", tools_enabled=True, memory_context=memory_context)
    return prompts.build_agent_planner_input("Q?", conversation_envelope="history", advisory=True, memory_context=memory_context)


def _plan(memory_context: str, *, indexed: bool) -> str:
    return prompts.build_multi_turn_planner_input("Fix it", planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30,
                                                  conversation_envelope="history", repo_map="map" if indexed else None,
                                                  memory_context=memory_context)


def test_both_prefix_builders_keep_their_cache_prefix_whatever_the_memory_holds() -> None:
    """ADR-039/041: memory sits after the cacheable prefix and before history. A change to memory, non-ASCII included, never
    moves a prefix byte or its boundary, and no memory leaves the prompt byte-identical to one without the argument."""
    first = ms.render(ms.select([_item(1, statement="Never push to main.")]))
    changed = ms.render(ms.select([_item(1, version=2, statement="Never push to main — não, 永不.")]))
    chat_prefix = prompts.indexed_chat_prefix(repo_map="map", tools_enabled=True)
    plan_prefix = prompts.indexed_planner_prefix(repo_map="map", tools_enabled=False, evidence_limits=None)
    for build, prefix in ((_chat, chat_prefix), (_plan, plan_prefix)):
        with_first, with_changed = build(first, indexed=True), build(changed, indexed=True)
        assert with_first.startswith(prefix) and with_changed.startswith(prefix)
        assert with_first[len(prefix):].lstrip("\n").startswith(ms.HEADER) and with_changed.encode()[: len(prefix.encode())] == prefix.encode()
        assert with_first.index(ms.HEADER) < with_first.index("history")  # memory before history
        assert build("", indexed=True) == build("", indexed=True) and ms.HEADER not in build("", indexed=True)
    for build in (_chat, _plan):  # without the index, memory still works and still precedes history
        text = build(changed, indexed=False)
        assert ms.HEADER in text and text.index(ms.HEADER) < text.index("history")


def test_no_memory_leaves_every_builder_byte_identical_to_before() -> None:
    assert prompts.build_agent_planner_input("Q?", conversation_envelope="history", advisory=True) == _chat("", indexed=False)
    assert prompts.build_multi_turn_planner_input("Fix it", planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30,
                                                  conversation_envelope="history", repo_map="map") == _plan("", indexed=True)
