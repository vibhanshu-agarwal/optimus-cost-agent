"""docs/README.md lists exactly the current documents: everything at a docs folder root."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tools.doc_paths import ARCHIVE_DIRNAME, DOCS_ROOT

INDEX = DOCS_ROOT / "README.md"
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\((?P<target>[^)#]+)(?:#[^)]*)?\)")
# Folders whose root holds current documents; each keeps its history in an archive/ beside them.
DOCUMENT_FOLDERS = (
    DOCS_ROOT,
    DOCS_ROOT / "decisions",
    DOCS_ROOT / "governance",
    DOCS_ROOT / "runbooks",
    DOCS_ROOT / "superpowers" / "plans",
    DOCS_ROOT / "superpowers" / "specs",
    DOCS_ROOT / "superpowers" / "reviews",
    DOCS_ROOT / "superpowers" / "reports",
)
# Folders that only group other folders, and publication bundles, which are listed as a whole.
GROUPING_FOLDERS = {DOCS_ROOT / name for name in ("decisions", "governance", "runbooks", "sources", "superpowers")} | {
    DOCS_ROOT / "superpowers" / name for name in ("plans", "specs", "reviews", "reports")
}
BUNDLE_FOLDERS = (DOCS_ROOT / "sources",)
# AGENTS.md keeps each reviewed plan's reviewer checkpoint log beside the reviews. The logs are
# gitignored working files, never published, so they are not current documents.
REVIEWS_ROOT = DOCS_ROOT / "superpowers" / "reviews"
REVIEWER_CHECKPOINT_SUFFIX = "-review-checkpoints.md"
REVIEWER_CHECKPOINT_IGNORE_RULE = "docs/superpowers/reviews/*-review-checkpoints.md"


def _is_reviewer_checkpoint_log(entry: Path) -> bool:
    return entry.parent == REVIEWS_ROOT and entry.name.endswith(REVIEWER_CHECKPOINT_SUFFIX)


def _current_documents() -> set[Path]:
    current: set[Path] = set()
    for folder in DOCUMENT_FOLDERS:
        for entry in folder.iterdir():
            if entry.name == ARCHIVE_DIRNAME or entry == INDEX or entry in GROUPING_FOLDERS:
                continue
            if _is_reviewer_checkpoint_log(entry):
                continue
            assert entry.is_file(), f"unexpected folder at a docs folder root: {entry}"
            current.add(entry.resolve())
    for folder in BUNDLE_FOLDERS:
        current.update(entry.resolve() for entry in folder.iterdir() if entry.name != ARCHIVE_DIRNAME)
    return current


def _indexed_documents() -> set[Path]:
    text = INDEX.read_text(encoding="utf-8")
    return {(INDEX.parent / match.group("target")).resolve() for match in MARKDOWN_LINK.finditer(text)}


def test_index_lists_every_current_document() -> None:
    missing = sorted(path.relative_to(DOCS_ROOT).as_posix() for path in _current_documents() - _indexed_documents())

    assert not missing, f"current documents missing from docs/README.md (list them or archive them): {missing}"


def test_index_lists_nothing_archived_or_missing() -> None:
    archives = {(folder / ARCHIVE_DIRNAME).resolve() for folder in (*DOCUMENT_FOLDERS, *BUNDLE_FOLDERS)}
    stale = sorted(
        path.relative_to(DOCS_ROOT).as_posix()
        for path in _indexed_documents() - _current_documents() - archives - {p.resolve() for p in GROUPING_FOLDERS}
    )

    assert not stale, f"docs/README.md links to documents that are not current: {stale}"


def test_only_gitignored_reviewer_checkpoint_logs_are_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gitignore = (DOCS_ROOT.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert REVIEWER_CHECKPOINT_IGNORE_RULE in gitignore, "the exclusion must cover only files git ignores"
    tracked = subprocess.run(
        ["git", "ls-files", "--", REVIEWER_CHECKPOINT_IGNORE_RULE],
        cwd=DOCS_ROOT.parent,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert tracked == "", f"a force-added checkpoint log would be a tracked document the index skips: {tracked}"
    assert _is_reviewer_checkpoint_log(REVIEWS_ROOT / "plan-9-review-checkpoints.md")
    assert not _is_reviewer_checkpoint_log(DOCS_ROOT / "superpowers" / "plans" / "plan-9-review-checkpoints.md")
    assert not _is_reviewer_checkpoint_log(REVIEWS_ROOT / "2026-10-01-plan-9-review.md")
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / "plan-9-review-checkpoints.md").write_text("log\n", encoding="utf-8")
    (reviews / "2026-10-01-unindexed-review.md").write_text("review\n", encoding="utf-8")
    monkeypatch.setitem(globals(), "REVIEWS_ROOT", reviews)
    monkeypatch.setitem(globals(), "DOCUMENT_FOLDERS", (reviews,))
    monkeypatch.setitem(globals(), "BUNDLE_FOLDERS", ())

    current = _current_documents()

    # The checkpoint log is skipped; an ordinary unindexed review still counts, so it would still fail.
    assert current == {(reviews / "2026-10-01-unindexed-review.md").resolve()}


def test_every_document_folder_has_an_archive() -> None:
    for folder in (*DOCUMENT_FOLDERS, *BUNDLE_FOLDERS):
        if folder in {DOCS_ROOT / "decisions", DOCS_ROOT / "governance"}:
            continue  # nothing has been retired from it yet
        assert (folder / ARCHIVE_DIRNAME).is_dir(), f"{folder} has no archive/ folder"
