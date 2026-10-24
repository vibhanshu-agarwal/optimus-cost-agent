"""EDIT directive grammar (#407): exact whole-line OLD/NEW blocks for one existing file."""

import pytest

from optimus.agent.directives import (
    AgentDirectiveParseError,
    AgentEditBlock,
    AgentEditDirective,
    AgentWriteDirective,
    bind_edit_base,
    parse_agent_plan,
)

_BASE = "a" * 64


def _edit(path: str, *blocks: tuple[str, str], header_suffix: str = "") -> str:
    lines = [f"EDIT {path}{header_suffix}"]
    for old, new in blocks:
        lines.append("<<<<<<< OLD")
        lines.extend(old.split("\n") if old else [])
        lines.append("======= NEW")
        lines.extend(new.split("\n") if new else [])
        lines.append(">>>>>>> END")
    return "\n".join(lines)


def test_edit_with_one_block_parses_old_and_new_lines():
    directives = parse_agent_plan("READ big.py\n" + _edit("big.py", ("def f():\n    return 1", "def f():\n    return 2")))

    assert directives.read_paths == ("big.py",)
    assert directives.write == AgentEditDirective(
        path="big.py",
        blocks=(AgentEditBlock(old_lines=("def f():", "    return 1"), new_lines=("def f():", "    return 2")),),
    )


def test_edit_allows_several_blocks_blank_lines_between_them_and_an_empty_new():
    plan = _edit("big.py", ("a", "b")) + "\n\n" + _edit("x", ("c", ""))[len("EDIT x\n") :] + "\nTEST pytest tests -q"

    directives = parse_agent_plan(plan)

    assert isinstance(directives.write, AgentEditDirective)
    assert directives.write.blocks == (
        AgentEditBlock(old_lines=("a",), new_lines=("b",)),
        AgentEditBlock(old_lines=("c",), new_lines=()),
    )
    assert directives.tests == (("pytest", "tests", "-q"),)


def test_block_bodies_are_opaque_to_directives():
    old = "READ other.py\nWRITE other.py\nTEST pytest x\nOBSERVE: note\nMCP_CALL s t {}\nEDIT other.py"
    directives = parse_agent_plan(_edit("big.py", (old, old)))

    assert directives.read_paths == ()
    assert directives.tests == ()
    assert directives.write.blocks[0].old_lines == tuple(old.split("\n"))
    assert directives.write.blocks[0].new_lines == tuple(old.split("\n"))


def test_block_lines_keep_their_exact_whitespace():
    directives = parse_agent_plan(_edit("big.py", ("    - item  ", "\t- item")))

    assert directives.write.blocks[0].old_lines == ("    - item  ",)
    assert directives.write.blocks[0].new_lines == ("\t- item",)


def test_bulleted_edit_header_is_accepted_like_other_directives():
    directives = parse_agent_plan("- " + _edit("big.py", ("a", "b")))

    assert directives.write.path == "big.py"


@pytest.mark.parametrize(
    "plan",
    (
        "EDIT big.py\nREAD big.py",  # no block
        "EDIT big.py",  # no block at all
        "EDIT big.py\n<<<<<<< OLD\na\n======= NEW\nb",  # unterminated NEW
        "EDIT big.py\n<<<<<<< OLD\na",  # unterminated OLD
        "EDIT big.py\n<<<<<<< OLD\n======= NEW\nb\n>>>>>>> END",  # empty OLD
        "EDIT big.py\n<<<<<<< OLD\na\n>>>>>>> END",  # END before NEW
        "EDIT big.py\n<<<<<<< OLD\na\n<<<<<<< OLD\nb\n======= NEW\nc\n>>>>>>> END",  # OLD inside OLD
        "EDIT big.py\n<<<<<<< OLD\na\n======= NEW\nb\n======= NEW\nc\n>>>>>>> END",  # NEW inside NEW
        "EDIT big.py\n<<<<<<< OLD\na\n======= NEW\nb\n<<<<<<< OLD\n>>>>>>> END",  # OLD inside NEW
        "EDIT big.py\nprose\n<<<<<<< OLD\na\n======= NEW\nb\n>>>>>>> END",  # text before the first block
        _edit("big.py", ("a", "b")) + "\nprose between blocks\n<<<<<<< OLD\nc\n======= NEW\nd\n>>>>>>> END",
        "READ big.py\n>>>>>>> END",  # stray marker outside an EDIT
        "READ big.py\n======= NEW",
        "READ big.py\n<<<<<<< OLD",
    ),
)
def test_malformed_edit_blocks_make_the_plan_unparseable(plan):
    with pytest.raises(AgentDirectiveParseError):
        parse_agent_plan(plan)


@pytest.mark.parametrize("header", ("EDIT", "EDIT ", "EDIT a.py b.py", "EDIT ../outside.py", "EDIT C:/abs.py", "EDIT /abs.py"))
def test_a_malformed_edit_header_never_leaves_a_read_only_plan(header):
    plan = f"READ big.py\n{header}\n<<<<<<< OLD\na\n======= NEW\nb\n>>>>>>> END"

    with pytest.raises(AgentDirectiveParseError):
        parse_agent_plan(plan)


def test_a_plan_holds_at_most_one_mutation_directive():
    with pytest.raises(AgentDirectiveParseError, match="at most one WRITE or EDIT"):
        parse_agent_plan(_edit("a.py", ("a", "b")) + "\n" + _edit("b.py", ("c", "d")))
    with pytest.raises(AgentDirectiveParseError, match="at most one WRITE or EDIT"):
        parse_agent_plan(_edit("a.py", ("a", "b")) + "\nWRITE b.py\ncontent")


def test_write_bodies_are_unchanged_and_keep_edit_and_marker_lines_as_content():
    plan = "WRITE notes.md\nEDIT big.py\n<<<<<<< OLD\n======= NEW\n>>>>>>> END\nREAD notes.md"

    directives = parse_agent_plan(plan)

    assert directives.write == AgentWriteDirective(  # #410 R2: the body keeps its own last terminator
        path="notes.md", content="EDIT big.py\n<<<<<<< OLD\n======= NEW\n>>>>>>> END\n"
    )
    assert directives.read_paths == ("notes.md",)


def test_model_plans_must_not_carry_a_base_and_stored_plans_must():
    unbound = _edit("big.py", ("a", "b"))
    bound = _edit("big.py", ("a", "b"), header_suffix=f" base_sha256={_BASE}")

    assert parse_agent_plan(unbound, edit_base="forbidden").write.base_sha256 is None
    assert parse_agent_plan(bound, edit_base="required").write.base_sha256 == _BASE
    with pytest.raises(AgentDirectiveParseError, match="base_sha256"):
        parse_agent_plan(bound, edit_base="forbidden")
    with pytest.raises(AgentDirectiveParseError, match="base_sha256"):
        parse_agent_plan(unbound, edit_base="required")
    # The default is lenient for callers that only classify a plan.
    assert parse_agent_plan(bound).write.base_sha256 == _BASE
    assert parse_agent_plan(unbound).write.base_sha256 is None


@pytest.mark.parametrize("suffix", (" base_sha256=" + "A" * 64, " base_sha256=" + "a" * 63, " base_sha256=", " sha256=" + "a" * 64))
def test_a_malformed_base_makes_the_plan_unparseable(suffix):
    with pytest.raises(AgentDirectiveParseError):
        parse_agent_plan(_edit("big.py", ("a", "b"), header_suffix=suffix))


def test_bind_edit_base_rewrites_only_the_header_and_keeps_every_other_byte():
    plan = "READ big.py\r\n- EDIT big.py\r\n<<<<<<< OLD\r\nEDIT big.py\r\n======= NEW\r\nb\r\n>>>>>>> END\r\nTEST pytest t -q\r\n"

    bound = bind_edit_base(plan, base_sha256=_BASE)

    assert bound == plan.replace("- EDIT big.py\r\n", f"- EDIT big.py base_sha256={_BASE}\r\n", 1)
    assert parse_agent_plan(bound, edit_base="required").write.blocks == parse_agent_plan(plan).write.blocks


def test_bind_edit_base_refuses_a_plan_without_an_unbound_edit():
    with pytest.raises(AgentDirectiveParseError):
        bind_edit_base("WRITE a.py\nx", base_sha256=_BASE)
    with pytest.raises(AgentDirectiveParseError):
        bind_edit_base(_edit("big.py", ("a", "b"), header_suffix=f" base_sha256={_BASE}"), base_sha256=_BASE)
    with pytest.raises(AgentDirectiveParseError):
        bind_edit_base(_edit("big.py", ("a", "b")), base_sha256="not-a-digest")


@pytest.mark.parametrize("separator", ("\u2028", "\u2029", "\x0b", "\x0c", "\x1c", "\x85"))
def test_edit_lines_end_only_at_cr_or_lf_so_other_separators_stay_content(separator):
    plan = f"EDIT a.py\n<<<<<<< OLD\nx{separator}y\n======= NEW\na{separator}b\n>>>>>>> END\n"

    edit = parse_agent_plan(plan).write

    assert edit.blocks == (AgentEditBlock(old_lines=(f"x{separator}y",), new_lines=(f"a{separator}b",)),)
    bound = bind_edit_base(plan, base_sha256=_BASE)
    assert bound == plan.replace("EDIT a.py\n", f"EDIT a.py base_sha256={_BASE}\n", 1)


def test_write_bodies_keep_a_separator_as_content():
    """#410 R1 supersedes the older split for WRITE: only LF and CRLF end a line, so U+2028 is body content."""
    assert parse_agent_plan("WRITE a.py\na\u2028b").write.content == "a\u2028b"


@pytest.mark.parametrize("marker", (">>>>>>> END", "======= NEW", "<<<<<<< OLD"))
def test_a_separator_before_marker_text_does_not_invent_a_marker_line(marker):
    plan = f"EDIT a.py\n<<<<<<< OLD\nx\u2028{marker}\n======= NEW\ny\n>>>>>>> END\n"

    assert parse_agent_plan(plan).write.blocks == (AgentEditBlock(old_lines=(f"x\u2028{marker}",), new_lines=("y",)),)


def test_an_edit_that_exists_only_under_the_older_split_is_rejected():
    # Under CR/LF lines this has no EDIT block; str.splitlines would invent one from the U+2028.
    with pytest.raises(AgentDirectiveParseError):
        parse_agent_plan("READ a.py\nnote\u2028EDIT a.py\u2028<<<<<<< OLD\u2028x\u2028======= NEW\u2028y\u2028>>>>>>> END\n")
