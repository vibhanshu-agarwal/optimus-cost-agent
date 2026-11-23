"""Plan 12.11 Task 4: what memory a turn is served and where it sits in the prompt (design spec v4 §5; ADR-039, ADR-041)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from context_engine.memory_contracts import ServedMemory
from optimus.agent import prompts
from optimus.context import memory_serving as ms
from optimus_security.sanitization import REDACTION_MASK


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
    # Codex CP4 review 16: the brief (non-ASCII too) sits in the same place, after memory, and never moves a prefix byte
    briefed = ms.with_brief(first, BRIEF + " — não, 永")
    for build, prefix in ((_chat, chat_prefix), (_plan, plan_prefix)):
        text = build(briefed, indexed=True)
        assert text.encode()[: len(prefix.encode())] == prefix.encode()
        assert text.index(ms.HEADER) < text.index(ms.BRIEF_HEADER) < text.index("history")
        assert build(ms.with_brief("", BRIEF), indexed=True).encode()[: len(prefix.encode())] == prefix.encode()  # brief alone


BRIEF = "**Welcome back.** Last work here: 2026-11-19 12:18 UTC (8 days ago), branch `main`, turn 1, outcome completed."


def test_the_brief_follows_memory_and_alone_still_forms_a_block() -> None:
    """Codex CP4 review 16: the brief the user was shown reaches the model after served memory; with nothing served it is the
    block by itself; no brief leaves the block byte-identical."""
    block = ms.render(ms.select([_item(1, statement="Never push to main.")]))
    assert ms.with_brief(block, None) == block and ms.with_brief("", None) == ""
    joined = ms.with_brief(block, BRIEF)
    assert joined.startswith(block) and joined.endswith(f"{ms.BRIEF_HEADER}\n{BRIEF}\n{ms.BRIEF_FOOTER}\n")
    assert ms.with_brief("", BRIEF) == f"{ms.BRIEF_HEADER}\n{BRIEF}\n{ms.BRIEF_FOOTER}\n"
    assert ms.with_brief("", "a", sanitize=lambda text: text.upper()) == f"{ms.BRIEF_HEADER}\nA\n{ms.BRIEF_FOOTER}\n"  # sanitized


def test_the_brief_yields_first_cut_on_a_character_boundary_and_memory_is_never_cut() -> None:
    """Plan v5: truncate the brief first. Protected memory keeps every byte; the brief gets what is left of the shared budget,
    cut inside a multi-byte character safely with its delimiters intact, and is replaced by a note when nothing is left."""
    brief = "Último trabalho: " + "永" * 6000  # 3 bytes a character: any cut can fall inside one
    for statements in (1, 40, 120):
        block = ms.render(ms.select([_item(n, statement=f"Rule {n}: " + "x" * 100) for n in range(statements)]))
        joined = ms.with_brief(block, brief)
        assert joined.startswith(block)  # memory first and whole
        assert len(joined.encode("utf-8")) <= max(ms.MEMORY_AND_BRIEF_MAX_BYTES, len(block.encode()) + len(ms.BRIEF_LEFT_OUT) + 1)
        tail = joined[len(block):]
        if len(block.encode()) < ms.MEMORY_AND_BRIEF_MAX_BYTES - 1024:
            assert tail.startswith(ms.BRIEF_HEADER) and tail.endswith(f"\n{ms.BRIEF_CUT}\n{ms.BRIEF_FOOTER}\n")
            assert "Último" in tail
        else:
            assert tail == f"{ms.BRIEF_LEFT_OUT}\n"
    roomy = ms.with_brief("", BRIEF)
    assert ms.BRIEF_CUT not in roomy  # a brief that fits is never marked
    assert prompts.build_agent_planner_input("Q?", conversation_envelope="history", advisory=True) == _chat("", indexed=False)
    assert prompts.build_multi_turn_planner_input("Fix it", planning_turn=1, max_planning_turns=3, remaining_wall_clock_minutes=30,
                                                  conversation_envelope="history", repo_map="map") == _plan("", indexed=True)


# --- #525: a workspace file name is not a secret -------------------------------------------------------------------------

RUNNER_ID = "tests/unit/tools/test_runner.py::TestLocalRunner::test_job_object"  # the entropy rule masks this id as a whole
BUILD_PATH = "docs/sources/agent-localized-edit/tools/build.py"


def _conversation(*known: str) -> Any:
    """The session's persistence sanitizer, as the session builds it (EVIDENCE_REDACTION_POLICY), with these known secrets."""
    from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs

    return ConversationSanitizer(ConversationSanitizerInputs(known_secrets=known, path_aliases=())).sanitize


def _persisted(text: str) -> str:
    return _conversation()(text)


def _aware(workspace: Path, *known: str) -> Any:
    """The session's sanitizer for this workspace, off the loop: it keeps the workspace's file names (#525, #530)."""
    from optimus.acp.conversation import ConversationSanitizer, ConversationSanitizerInputs

    return ConversationSanitizer(ConversationSanitizerInputs(known_secrets=known, path_aliases=()), workspace=workspace).sanitize_in_workspace


def _secret() -> str:
    """A random-looking key, made when the test runs so no file holds it: letters and digits only, so it fits a test name."""
    import base64
    import hashlib

    return "K" + "".join(ch for ch in base64.b64encode(hashlib.sha256(b"memory-525").digest()).decode() if ch.isalnum())


def _prefixed() -> str:
    return "sk-" + "ant-" + "abcdefghijklmnopqrstuvwx"  # a key prefix the prefix rule masks, spelled apart for the secret scan


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    for name in ("tests/unit/tools/test_runner.py", BUILD_PATH, "build/generated/LocalRunnerOutputCollector.py",
                 f"docs/keys/{_prefixed()}.md"):
        (workspace / name).parent.mkdir(parents=True, exist_ok=True)
        (workspace / name).write_text("x = 1\n", encoding="utf-8")
    (workspace / ".gitignore").write_text("build/\n", encoding="utf-8")
    return workspace


@pytest.mark.parametrize("note", [f"Run {RUNNER_ID} before committing.", f"Run {BUILD_PATH} first.",
                                  f"See {BUILD_PATH}: it builds the doc.", f"Both `{RUNNER_ID}` and {BUILD_PATH}."])
def test_a_note_naming_workspace_files_is_kept_as_written(tmp_path: Path, note: str) -> None:
    assert _persisted(note) != note  # the false refusal: the entropy rule takes each name for a random token
    assert _aware(_workspace(tmp_path))(note) == note


def test_secrets_beside_or_inside_a_workspace_file_name_are_still_masked(tmp_path: Path) -> None:
    sanitize, secret = _aware(_workspace(tmp_path)), _secret()
    assert _persisted(secret) != secret  # the key alone is masked by the same rule
    beside = sanitize(f"Run {RUNNER_ID} with the key {secret} set.")
    assert beside == f"Run {RUNNER_ID} with the key {REDACTION_MASK} set."
    # a key written as a test name, glued to a name, or behind a character no path holds leaves the whole token judged
    for word in (f"tests/unit/tools/test_runner.py::{secret}", f"{secret}/tests/unit/tools/test_runner.py",
                 f"x+{BUILD_PATH}", f"{BUILD_PATH}{secret}"):
        out = sanitize(f"See {word} now.")
        assert secret not in out and out == _persisted(f"See {word} now.") != f"See {word} now.", word


def test_every_other_rule_still_reads_a_workspace_file_name(tmp_path: Path) -> None:
    """Codex round 114, finding 1: an exact known secret spelled across a test id's names, or inside a path, and a key prefix in
    a real file's name, are masked as before. Only the entropy rule skips an exempt name."""
    workspace = _workspace(tmp_path)
    for known, note in (("TestLocalRunner::test_job_object", f"Run {RUNNER_ID} before committing."),
                        ("agent-localized-edit", f"Run {BUILD_PATH} first.")):
        out = _aware(workspace, known)(note)
        assert known not in out and out == _conversation(known)(note) != note, known
    keyed = f"Read docs/keys/{_prefixed()}.md first."
    out = _aware(workspace)(keyed)
    assert _prefixed() not in out and out == _persisted(keyed)


@pytest.mark.parametrize("named", ["tests/unit/tools/test_missing_runner.py::TestLocalRunner",  # no such file
                                   "build/generated/LocalRunnerOutputCollector.py",  # ignored by the workspace
                                   f"../ws/{BUILD_PATH}"])  # spelled through the parent
def test_a_name_that_is_not_a_file_the_workspace_admits_is_judged_as_before(tmp_path: Path, named: str) -> None:
    note = f"Run {named} first."
    assert _persisted(note) != note
    assert _aware(_workspace(tmp_path))(note) == _persisted(note)


def test_a_rule_that_takes_the_name_takes_it_as_before(tmp_path: Path) -> None:
    sanitize = _aware(_workspace(tmp_path))
    assert sanitize(f"password {RUNNER_ID}") == _persisted(f"password {RUNNER_ID}") != f"password {RUNNER_ID}"


def test_each_distinct_name_is_looked_at_once_and_no_file_is_opened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex round 114, finding 2: a statement repeating a name costs one gate check, and no file's bytes are read."""
    from optimus.guardrails.file_policy import FilePolicy

    looked: list[str] = []

    class Counting(FilePolicy):
        def admitter(self) -> Any:
            admits = super().admitter()
            return lambda relative: looked.append(relative) or admits(relative)

        def read(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a file was opened")

        def decide(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("a file was opened")

    monkeypatch.setattr(ms, "FilePolicy", Counting)
    note = " ".join([f"Run {RUNNER_ID}."] * 100)
    assert _aware(_workspace(tmp_path))(note) == note
    assert looked == ["tests/unit/tools/test_runner.py"]


def test_the_exempt_word_is_the_sanitizers_whole_token() -> None:
    """The exempt word must be exactly what the entropy rule reads as one token, or a key could sit beside a name in it."""
    from optimus_security import sanitization

    assert ms._SANITIZER_RUN.pattern.split("]")[0] == sanitization._TOKEN_CANDIDATE_RE.pattern.split("]")[0]
    assert ms._ENTROPY_TOKEN_LENGTHS == (sanitization._ENTROPY_MIN_LEN, sanitization._ENTROPY_MAX_LEN)


def test_at_most_max_name_checks_words_reach_the_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#530: the conversation sanitizer sees whole replies, so a text naming many files costs at most MAX_NAME_CHECKS checks."""
    from optimus.guardrails.file_policy import FilePolicy

    looked: list[str] = []

    class Counting(FilePolicy):
        def admitter(self) -> Any:
            admits = super().admitter()
            return lambda relative: looked.append(relative) or admits(relative)

    monkeypatch.setattr(ms, "FilePolicy", Counting)
    words = [f"tests/unit/tools/test_generated_{n:03d}.py" for n in range(ms.MAX_NAME_CHECKS + 6)]
    ms.workspace_names(" ".join(words), _workspace(tmp_path), _persisted)
    assert looked == words[: ms.MAX_NAME_CHECKS]
