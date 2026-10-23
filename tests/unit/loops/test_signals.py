from __future__ import annotations

from optimus.loops.signals import ActionKind, McpResults, ReadCoverage, ReadResult, mcp_step, parse_failure_step, read_step

SHA_A = "a" * 64
SHA_B = "b" * 64


def _read(start: int, end: int, sha: str = SHA_A, path: str = "src/a.py") -> ReadResult:
    return ReadResult(path=path, start_byte=start, end_byte=end, source_sha256=sha)


def test_a_fully_covered_re_read_of_unchanged_content_is_not_novel():
    coverage = ReadCoverage()
    assert read_step([_read(0, 100)], coverage).novel
    assert not read_step([_read(0, 100)], coverage).novel
    assert not read_step([_read(10, 50)], coverage).novel


def test_a_read_covered_only_by_two_earlier_ranges_together_is_not_novel():
    coverage = ReadCoverage()
    read_step([_read(0, 50)], coverage)
    read_step([_read(50, 100)], coverage)
    assert not read_step([_read(20, 80)], coverage).novel


def test_a_partly_unread_range_is_novel():
    coverage = ReadCoverage()
    read_step([_read(0, 50)], coverage)
    assert read_step([_read(40, 60)], coverage).novel


def test_a_changed_file_is_novel_even_for_a_covered_range():
    coverage = ReadCoverage()
    read_step([_read(0, 100)], coverage)
    step = read_step([_read(0, 100, sha=SHA_B)], coverage)
    assert step.novel
    assert step.result_digest == SHA_B


def test_a_read_fingerprint_is_the_exact_ranges_and_the_digest_their_hashes():
    step = read_step([_read(5, 9, path="b.py"), _read(0, 4)], ReadCoverage())
    assert step.kind is ActionKind.READ
    assert step.fingerprint == "READ:b.py#bytes=5:9|src/a.py#bytes=0:4"
    assert step.result_digest == f"{SHA_A}|{SHA_A}"


def test_an_mcp_fingerprint_separates_tools_and_arguments_on_one_server():
    seen = McpResults()
    one = mcp_step(operation="call", server="s", tool="t1", arguments={"a": 1}, evidence_envelope="x", results=seen)
    two = mcp_step(operation="call", server="s", tool="t2", arguments={"a": 1}, evidence_envelope="y", results=seen)
    three = mcp_step(operation="call", server="s", tool="t1", arguments={"a": 2}, evidence_envelope="z", results=seen)
    assert len({one.fingerprint, two.fingerprint, three.fingerprint}) == 3
    reordered = mcp_step(
        operation="call", server="s", tool="t1", arguments={"b": 2, "a": 1}, evidence_envelope="x", results=McpResults()
    )
    assert reordered.fingerprint == mcp_step(
        operation="call", server="s", tool="t1", arguments={"a": 1, "b": 2}, evidence_envelope="x", results=McpResults()
    ).fingerprint


def test_an_mcp_result_is_novel_only_the_first_time_its_envelope_is_seen():
    seen = McpResults()
    first = mcp_step(operation="call", server="s", tool="t", arguments={}, evidence_envelope="out", results=seen)
    again = mcp_step(operation="call", server="s", tool="t", arguments={}, evidence_envelope="out", results=seen)
    changed = mcp_step(operation="call", server="s", tool="t", arguments={}, evidence_envelope="out2", results=seen)
    assert (first.novel, again.novel, changed.novel) == (True, False, True)
    assert first.result_digest == again.result_digest != changed.result_digest


def test_an_mcp_result_that_changed_since_the_calls_last_one_is_novel_even_if_seen_before():
    seen = McpResults()
    novelty = [
        mcp_step(operation="call", server="s", tool="t", arguments={}, evidence_envelope=out, results=seen).novel
        for out in ("A", "B", "A", "B", "B")
    ]
    assert novelty == [True, True, True, True, False]


def test_another_call_returning_evidence_already_seen_is_not_novel():
    seen = McpResults()
    mcp_step(operation="call", server="s", tool="t", arguments={"q": 1}, evidence_envelope="same", results=seen)
    assert not mcp_step(operation="call", server="s", tool="t", arguments={"q": 2}, evidence_envelope="same", results=seen).novel


def test_a_file_whose_hash_changed_since_its_last_read_is_novel_even_for_a_covered_range():
    coverage = ReadCoverage()
    novelty = [read_step([_read(0, 10, sha=sha)], coverage).novel for sha in (SHA_A, SHA_B, SHA_A, SHA_A)]
    assert novelty == [True, True, True, False]


def test_a_parse_failure_carries_its_code_and_is_never_novel():
    step = parse_failure_step(code="GRAMMAR_UNRECOGNIZED", message="no recognized planning-turn grammar")
    assert (step.kind, step.fingerprint, step.error_class, step.novel) == (
        ActionKind.PARSE_FAILURE,
        "PARSE:GRAMMAR_UNRECOGNIZED",
        "GRAMMAR_UNRECOGNIZED",
        False,
    )
