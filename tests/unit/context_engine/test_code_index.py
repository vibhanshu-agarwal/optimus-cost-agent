"""Plan 12.10 Task 3: what the parser lets out of the engine. The real-store proof is tests/integration/context/test_memory_b1_canaries.py."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("tree_sitter")

from context_engine.code_index import MAX_PROSE_CHARS, language_for, parse_file, path_id, split_terms  # noqa: E402

_PY = b'''"""DOCCANARY"""
from pkg.mod import thing

VALUE = "LITERALCANARY"


class Foo(Base):
    """CLASSDOCCANARY"""

    def bar(self, first=1, second="DEFAULTCANARY") -> int:  # COMMENTCANARY
        # INNERCOMMENTCANARY
        value = compute("BODYCANARY")
        return value + innerCall(first)


def top():
    pass
'''
_JAVA = b'''package a.b;
import java.util.List;
/** JAVADOCCANARY */
@Deprecated(since="ANNOTCANARY")
public class Widget extends Base {
  public int size(String name) { return call("STRCANARY"); } // COMMENTCANARY
  interface Inner { void go(); }
  Widget() {}
}
'''
_CANARIES = ("DOCCANARY", "LITERALCANARY", "DEFAULTCANARY", "COMMENTCANARY", "BODYCANARY", "JAVADOCCANARY", "ANNOTCANARY", "STRCANARY", "SNIPPETCANARY")


def _wire(path: str, data: bytes) -> str:
    return json.dumps([record.wire() for record in parse_file(path, data).records])


@pytest.mark.parametrize(("path", "data"), [("pkg/a.py", _PY), ("a/Widget.java", _JAVA)])
def test_nothing_from_a_body_comment_or_literal_leaves_the_engine(path: str, data: bytes) -> None:
    wire = _wire(path, data)
    assert [canary for canary in _CANARIES if canary in wire or canary.lower() in wire] == []


def test_the_embedder_may_see_what_the_store_may_not() -> None:
    bar = next(record for record in parse_file("pkg/a.py", _PY).records if record.symbol == "Foo.bar")
    assert bar.embed_text is not None and "BODYCANARY" in bar.embed_text
    assert "embed_text" not in bar.wire()


def test_python_symbols_are_qualified_and_located() -> None:
    parsed = parse_file("pkg/a.py", _PY, modified=7)
    symbols = {record.symbol: record for record in parsed.records if record.kind == "symbol"}
    assert sorted(symbols) == ["Foo", "Foo.bar", "top"]
    assert symbols["Foo.bar"].signature == 'def bar(self, first=1, second="...") -> int'
    assert (symbols["top"].start_line, symbols["top"].end_line) == (16, 17)
    assert symbols["Foo.bar"].modified == 7
    assert parsed.language == "python" and parsed.parsed_lines == 11


def test_java_symbols_are_qualified() -> None:
    parsed = parse_file("a/Widget.java", _JAVA)
    symbols = {record.symbol: record for record in parsed.records if record.kind == "symbol"}
    assert sorted(symbols) == ["Widget", "Widget.Inner", "Widget.Inner.go", "Widget.Widget", "Widget.size"]
    assert symbols["Widget"].signature == '@Deprecated(since="...") public class Widget extends Base'
    assert symbols["Widget.size"].signature == "public int size(String name)"


def test_imports_are_recorded_as_observed_structure() -> None:
    file_record = parse_file("pkg/a.py", _PY).records[0]
    assert file_record.kind == "file" and file_record.description == "imports: pkg.mod"
    java = parse_file("a/Widget.java", _JAVA).records[0]
    assert java.description is not None and "java.util.List" in java.description


def test_a_changed_file_gets_new_record_ids_and_the_same_path_id() -> None:
    first, second = parse_file("a.py", b"def f(): pass\n"), parse_file("a.py", b"def f(): return 1\n")
    assert first.file_hash != second.file_hash
    assert {record.id for record in first.records}.isdisjoint(record.id for record in second.records)
    assert first.records[0].path_id == second.records[0].path_id == path_id("a.py")


def test_parsing_is_deterministic() -> None:
    assert parse_file("pkg/a.py", _PY).records == parse_file("pkg/a.py", _PY).records


def test_a_syntax_error_still_indexes_what_it_can_and_says_so() -> None:
    parsed = parse_file("broken.py", b"def good():\n    pass\n\ndef broken(:\n")
    assert parsed.parse_errors is True
    assert "good" in {record.symbol for record in parsed.records}


def test_a_document_keeps_its_prose_and_only_the_names_of_its_code() -> None:
    parsed = parse_file("docs/a.md", b'# Title\nSome prose.\n```python\ndef hidden():  # SNIPPETCANARY\n    return "SNIPPETCANARY"\n```\n## Next\nMore.\n')
    sections = [record for record in parsed.records if record.kind == "section"]
    assert [(record.symbol, record.prose) for record in sections] == [("Title", "Some prose."), ("Next", "More.")]
    assert "hidden" in sections[0].terms and "with code" in (sections[0].description or "")
    assert "snippetcanary" not in json.dumps([record.wire() for record in parsed.records]).lower()
    assert sections[0].embed_text is not None and "SNIPPETCANARY" in sections[0].embed_text


def test_long_prose_is_split_at_the_limit() -> None:
    parsed = parse_file("a.md", ("# T\n" + "word " * MAX_PROSE_CHARS).encode())
    sections = [record for record in parsed.records if record.kind == "section"]
    assert len(sections) > 1 and all(len(record.prose or "") <= MAX_PROSE_CHARS for record in sections)
    assert len({record.id for record in sections}) == len(sections)


@pytest.mark.parametrize(("path", "data"), [("main.kt", b'fun main() { println("KOTLIN") }'), ("binary.py", b"\xff\xfe\x00")])
def test_what_cannot_be_parsed_is_listed_and_counts_no_lines(path: str, data: bytes) -> None:
    parsed = parse_file(path, data)
    assert parsed.parsed_lines == 0 and parsed.language == "unsupported" and [record.kind for record in parsed.records] == ["file"]
    assert "KOTLIN" not in json.dumps(parsed.records[0].wire()) and "kotlin" not in parsed.records[0].terms


@pytest.mark.parametrize(("path", "language"), [("a.py", "python"), ("A.JAVA", "java"), ("x/y.md", "markdown"), ("r.txt", "text"), ("Makefile", "unsupported"), ("a.kt", "unsupported")])
def test_languages(path: str, language: str) -> None:
    assert language_for(path) == language


def test_terms_are_split_lowercased_and_lose_their_order() -> None:
    assert split_terms(["fetchHTTPResponse snake_case_name"]) == "case fetch fetchhttpresponse http name response snake snake_case_name"


def test_importing_the_engine_needs_no_optional_package() -> None:
    import subprocess
    import sys

    probe = "import sys\nsys.modules['tree_sitter'] = None\nimport context_engine.code_index, context_engine.index_worker\nprint('ok')"
    result = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)
    assert result.stdout.strip() == "ok", result.stderr


def _prose_of(path: str, text: str) -> str:
    parsed = parse_file(path, text.encode("utf-8"))
    return "\n".join(record.prose or "" for record in parsed.records) + "\n".join(record.symbol or "" for record in parsed.records)


def _terms_of(path: str, text: str) -> str:
    return " ".join(record.terms for record in parse_file(path, text.encode("utf-8")).records)


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("a.md", "Before\n\n    run('LEAK')\n\nAfter\n"),
        ("a.md", "Before\n\n\trun('LEAK')\n"),
        ("a.md", "`````\n```\nLEAK\n```\n`````\n"),
        ("a.md", "~~~~\n~~~\nLEAK\n~~~~\n"),
        ("a.md", "Call `LEAK` now\n"),
        ("a.md", "Call ``run(`LEAK`)`` now\n"),
        ("a.md", "A stray ` then LEAK\n"),
        ("a.md", "<pre>\nLEAK\n</pre>\n"),
        ("a.md", "<code>LEAK</code>\n"),
        ("a.md", "<pre>\n# Example\nprint('LEAK')\n</pre>\n"),
        ("a.md", "Before <pre>\nLEAK\n"),
        ("a.md", "<script>\n# Heading\nLEAK\n</script>\n"),
        ("a.md", "<pre>\n</prefix>\n# Heading\nLEAK\n</pre>\n"),
        ("a.md", "<code>x</code><pre>\nLEAK\n"),
        ("a.md", "<pre>\nx\n</pre><pre>\n# Heading\nLEAK\n</pre>\n"),
        ("a.md", "<code>x</code><pre>\n# Heading\nLEAK\n</pre>\n"),
        ("a.md", "<!--\n# Heading\nLEAK\n-->\n"),
        ("a.md", "<!-- LEAK -->\n"),
        ("a.md", "<textarea>\n# Heading\nLEAK\n</textarea>\n"),
        ("a.md", "<PRE CLASS='x'>\n# Heading\nLEAK\n</PRE >\n"),
        ("a.md", ">>> LEAK\n"),
        ("a.md", "# Using `LEAK`\nText\n"),
        ("a.md", "```\nnever closed\nLEAK\n"),
        ("a.rst", "Text::\n\n  LEAK = 1\n"),
        ("a.rst", ".. code-block:: python\n\n   LEAK = 1\n"),
        ("a.rst", ".. LEAK\n"),
        ("a.txt", "Text\n\n  LEAK = 1\n"),
    ],
    ids=["indented", "tab", "long-backtick-fence", "long-tilde-fence", "inline", "double-backtick-inline", "stray-backtick", "pre", "code", "pre-across-a-heading", "pre-never-closed", "script", "lookalike-closing-tag", "second-block-on-a-line", "closed-and-reopened-on-a-line", "second-block-across-a-heading", "comment-across-a-heading", "comment", "textarea", "uppercase-with-attributes", "doctest", "heading-span", "unclosed-fence",
         "rst-literal", "rst-directive", "rst-comment", "text-indented"],
)
def test_nothing_that_may_be_code_reaches_prose(path: str, text: str) -> None:
    assert "LEAK" not in _prose_of(path, text)


@pytest.mark.parametrize(
    "block",
    ['x = """\nLEAK\n"""', "x = '''\nLEAK\n'''", "/* LEAK\n*/", "<!-- LEAK\n-->", 'x = "a\\"LEAK"', 'x = "LEAK', "x = 1  # LEAK", "x = 1  // LEAK", "SELECT 1 -- LEAK"],
    ids=["triple-double", "triple-single", "block-comment", "html-comment", "escaped-quote", "unterminated", "hash", "slashes", "sql"],
)
def test_strings_and_comments_of_document_code_stay_out_of_its_terms(block: str) -> None:
    assert "leak" not in _terms_of("a.md", f"```\n{block}\nvisible_name\n```\n")
    assert "visible_name" in _terms_of("a.md", f"```\nvisible_name\n{block}\n```\n") or "\n" in block


def test_ordinary_prose_survives_and_a_code_blocks_names_are_terms() -> None:
    text = "# Guide\nA plain sentence stays.\n\n- a list item stays\n\n```\ncompute_total(items)\n```\n"
    assert "A plain sentence stays." in _prose_of("a.md", text) and "a list item stays" in _prose_of("a.md", text)
    assert "compute_total" in _terms_of("a.md", text)


def test_prose_after_a_closed_html_block_stays() -> None:
    text = "<pre>\nhidden\n</pre>\nThis sentence stays.\n"
    assert "This sentence stays." in _prose_of("a.md", text) and "hidden" not in _prose_of("a.md", text)
