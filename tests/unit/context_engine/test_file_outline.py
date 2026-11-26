"""Plan 12.14 Task 3 (D4): the overflow outline. Only a direct summary task, only beyond the hard ceiling, only one required file, only a
structure the parser understands, and always disclosed; otherwise the pack is exactly what it was."""

from __future__ import annotations

import hashlib

import pytest

from context_engine.context_pack import SECTION_REQUIRED, assemble_pack
from context_engine.file_outline import DISCLOSURE, OUTLINE_MAX_TOKENS, OUTLINE_VERSION, build_outline, summary_target
from context_engine.retrieval import Hit, Ranked

BODY_MARKER = "BODY_ONLY_TEXT_NEVER_IN_AN_OUTLINE"


def _big(functions: int = 400) -> bytes:
    """A Python file whose whole text is far over a small ceiling; every body carries a marker an outline must never show."""
    return "".join(f"def handler_{i}(event, context):\n    return '{BODY_MARKER} {i}'\n\n\n" for i in range(functions)).encode()


def tokens(text: str) -> int:
    return len(text.encode("utf-8"))


OTHER = b"class Loader:\n    def load(self):\n        return 1\n"
RANKED = [Ranked(Hit(id="o", kind="symbol", path="other.py", file_hash=hashlib.sha256(OTHER).hexdigest(), symbol="Loader", signature="class Loader:",
                     start_line=1, end_line=3), 0.5, {"lexical": 1})]


def _pack(files: dict[str, bytes | None], required: tuple[str, ...], *, overview: str | None, budget: int = 4_000, target: int | None = 2_000):
    return assemble_pack(required=required, ranked=RANKED, read=lambda path: files.get(path), estimate=tokens, budget_tokens=budget, target_tokens=target,
                         overview_path=overview)


# --- the direct task ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("task", ['Summarize "src/big.py"', '  Summarize "src/big.py"\n'])
def test_only_the_bare_summary_request_names_a_target(task):
    assert summary_target(task) == "src/big.py"


@pytest.mark.parametrize("task", [
    'Summarize "src/big.py" and fix the failing handler',  # additional edit intent
    'Summarize "src/big.py"\nThen quote lines 3-9 exactly.',  # a second line
    'Please Summarize "src/big.py"',  # other words first
    'Here is a note: "Summarize "src/big.py"" from the wiki',  # nested, quoted text
    "Summarize 'src/big.py'", "Summarize src/big.py", 'summarize "src/big.py"', 'Summarize ""', 'Summarize "a.py" "b.py"',
    'Quote exactly the lines of "src/big.py" that define handler_3.',
    'Summarize "docs/ops guide.md"', 'Summarize "docs/r\u00e9sum\u00e9.md"', 'Summarize "src\\big.py"', 'Summarize "src/big"',  # Codex CP2 A1
])
def test_any_other_task_names_no_target(task):
    assert summary_target(task) is None


# --- the outline ----------------------------------------------------------------------------------------------------------


def test_an_outline_lists_entries_in_order_with_ranges_and_discloses_itself_and_never_a_body():
    data = _big(5)
    outline = build_outline("src/big.py", data, estimate=tokens, max_tokens=OUTLINE_MAX_TOKENS)
    assert outline is not None and BODY_MARKER not in outline.text
    assert DISCLOSURE in outline.text and f"sha256 {hashlib.sha256(data).hexdigest()}, {len(data)} bytes" in outline.text
    assert outline.ranges == ((1, 2), (5, 6), (9, 10), (13, 14), (17, 18)) and "1-2 def handler_0(event, context)\n" in outline.text
    meta = outline.metadata("src/big.py")
    assert meta["generator"] == OUTLINE_VERSION and meta["entries_shown"] == 5 and meta["entries_omitted"] == 0 and meta["reread_required"] is True
    assert meta["representation_sha256"] == hashlib.sha256(outline.text.encode()).hexdigest() and "text" not in meta


def test_an_outline_over_its_limit_keeps_the_first_entries_and_counts_the_rest():
    outline = build_outline("src/big.py", _big(400), estimate=tokens, max_tokens=50_000)
    assert outline is not None and tokens(outline.text) <= OUTLINE_MAX_TOKENS, "never above 2,048 estimated tokens, whatever room it is given"
    shown = len(outline.ranges)
    assert 0 < shown < 400 and f"Omitted: the {400 - shown} later entries, not listed here." in outline.text
    assert outline.metadata("src/big.py")["entries_omitted"] == 400 - shown


def test_a_document_is_outlined_by_its_headings():
    data = b"# Guide\n\nIntro prose BODY.\n\n## Install\n\nSteps BODY.\n"
    outline = build_outline("docs/guide.md", data, estimate=tokens, max_tokens=OUTLINE_MAX_TOKENS)
    assert outline is not None and "Guide" in outline.text and "Install" in outline.text and "BODY" not in outline.text


@pytest.mark.parametrize(("path", "data"), [("src/big.rs", b"fn main() {}\n" * 10), ("src/big.py", b"\xff\xfe not utf-8"), ("src/flat.py", b"x = 1\n" * 50),
                                           ("logs/run.txt", b"2026-11-25 a log line with no heading\n" * 3_000),  # Fable CP2 finding 1
                                           ("docs/plain.md", b"Prose without a single heading.\n" * 2_000)],
                         ids=["rust", "not-utf8", "flat-python", "headingless-text", "headingless-markdown"])
def test_without_a_structure_the_parser_understands_there_is_no_outline(path, data):
    assert build_outline(path, data, estimate=tokens, max_tokens=OUTLINE_MAX_TOKENS) is None


def test_a_long_section_is_one_entry_not_one_per_piece():
    """Fable CP2 finding 1: the parser splits a long section into pieces with one heading and range; the outline lists it once."""
    data = b"# Guide\n\n" + b"Prose BODY line.\n" * 2_000 + b"\n## Install\n\nSteps.\n"
    outline = build_outline("docs/guide.md", data, estimate=tokens, max_tokens=OUTLINE_MAX_TOKENS)
    assert outline is not None and "(outline: 2 entries)" in outline.text and outline.text.count(" Guide") == 1 and len(outline.ranges) == 2


def test_an_outline_whose_first_entry_does_not_fit_is_none():
    assert build_outline("src/big.py", _big(3), estimate=tokens, max_tokens=50) is None


# --- the pack -------------------------------------------------------------------------------------------------------------


def test_a_summary_target_that_fits_the_ceiling_is_sent_whole():
    small = _big(3)
    pack = _pack({"src/big.py": small, "other.py": OTHER}, ("src/big.py",), overview="src/big.py")
    assert pack.complete and pack.outline is None and BODY_MARKER in pack.text and pack.selected[0].disclosure == "required"


def test_over_the_ceiling_the_summary_target_is_outlined_disclosed_and_optional_room_still_filled():
    data = _big()
    pack = _pack({"src/big.py": data, "other.py": OTHER}, ("src/big.py",), overview="src/big.py")
    assert pack.complete and BODY_MARKER not in pack.text and pack.text.startswith(f"{SECTION_REQUIRED}\n--- src/big.py (outline: 400 entries) ---\n{DISCLOSURE}")
    first = pack.selected[0]
    assert (first.path, first.disclosure, first.file_hash) == ("src/big.py", "outline", hashlib.sha256(data).hexdigest())
    # Fable CP2 finding 2: file_sha256s names files whose bytes the text shows; the outline's source hash stays on its row and metadata.
    assert "src/big.py" not in pack.file_sha256s and pack.outline["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert "class Loader:" in pack.text and pack.tokens <= pack.budget_tokens <= 4_000, "the chosen budget still governs the rest"


@pytest.mark.parametrize(("files", "required", "overview", "target"), [
    ({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py",), None, 2_000),  # no summary task
    ({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py",), "src/big.py", None),  # legacy budget: no hard ceiling, M2a's refusal
    ({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py", "other.py"), "src/big.py", 2_000),  # another required file: never implied
    ({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py",), "src/other.py", 2_000),  # the target is not the required file
    ({"src/big.rs": b"fn main() {}\n" * 2_000}, ("src/big.rs",), "src/big.rs", 2_000),  # unsupported: keeps TOO_LARGE
    ({"src/big.py": None}, ("src/big.py",), "src/big.py", 2_000),  # deleted, or refused by the policy now
])
def test_otherwise_the_pack_is_todays_refusal(files, required, overview, target):
    pack = _pack(files, required, overview=overview, target=target)
    assert not pack.complete and pack.outline is None and BODY_MARKER not in pack.text


def test_an_outline_that_cannot_fit_the_ceiling_is_todays_refusal():
    pack = _pack({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py",), overview="src/big.py", budget=60, target=40)
    assert not pack.complete and pack.text == "" and pack.missing_required == ("src/big.py",)


def test_each_pack_outlines_the_bytes_read_now():
    """No cache: an edit, an unsaved buffer or a rename shows in the next pack's outline, from that read."""
    before = _big()
    after = before.replace(b"def handler_0(event, context):", b"def renamed_entry(event):")
    first = _pack({"src/big.py": before}, ("src/big.py",), overview="src/big.py")
    second = _pack({"src/big.py": after}, ("src/big.py",), overview="src/big.py")
    assert "renamed_entry" not in first.text and "1-2 def renamed_entry(event)\n" in second.text
    assert first.outline["source_sha256"] != second.outline["source_sha256"] == hashlib.sha256(after).hexdigest()


def test_under_a_small_ceiling_the_outline_is_sized_to_fit_once_its_section_header_is_added():
    """A ceiling below the 2,048-token cap: the outline is sized to the room left after the section header, so it still fits C wrapped
    (an outline sized to all of C overflowed once the header was added; found by the Q-release gate's outline proofs)."""
    pack = _pack({"src/big.py": _big(), "other.py": OTHER}, ("src/big.py",), overview="src/big.py", budget=600, target=500)
    assert pack.complete and pack.outline is not None and pack.outline["section_tokens"] <= 600 and pack.tokens <= pack.budget_tokens <= 600
