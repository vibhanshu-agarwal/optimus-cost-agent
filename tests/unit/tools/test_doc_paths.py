"""Name-based document lookup and archive-tolerant link resolution (tools/doc_paths.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import doc_paths
from tools.doc_paths import DOCS_ROOT, doc_path, link_resolves, repo_relative, resolves_with_archive

BACKLOG = "2026-07-23-consolidated-deferred-followups-backlog.md"
ARCHIVED_SPEC = "2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-design.md"


def test_doc_path_finds_a_document_by_name_or_by_any_stale_repository_path() -> None:
    expected = "docs/superpowers/specs/archive/" + ARCHIVED_SPEC

    assert repo_relative(doc_path(ARCHIVED_SPEC)) == expected
    assert repo_relative(doc_path("docs/superpowers/specs/" + ARCHIVED_SPEC)) == expected
    assert repo_relative(doc_path(BACKLOG)) == "docs/superpowers/plans/" + BACKLOG


def test_doc_path_rejects_a_missing_document() -> None:
    with pytest.raises(LookupError, match="found \\[\\]"):
        doc_path("no-such-document.md")


def test_doc_path_rejects_an_ambiguous_name(monkeypatch: pytest.MonkeyPatch) -> None:
    duplicate = (DOCS_ROOT / "a" / "x.md", DOCS_ROOT / "b" / "x.md")
    monkeypatch.setattr(doc_paths, "_docs_by_name", lambda: {"x.md": duplicate})

    with pytest.raises(LookupError, match="exactly one"):
        doc_path("x.md")


def test_document_names_under_docs_are_unique() -> None:
    duplicates = {name: paths for name, paths in doc_paths._docs_by_name().items() if len(paths) > 1}

    assert not duplicates, f"document names under docs/ must be unique: {duplicates}"


def test_a_reference_survives_a_move_into_or_out_of_archive() -> None:
    specs = DOCS_ROOT / "superpowers" / "specs"
    moved_bundle_file = DOCS_ROOT / "sources" / "local-gateway-architecture-v3" / "verification.md"

    assert resolves_with_archive(specs / ARCHIVED_SPEC)  # the file now lives in specs/archive/
    assert resolves_with_archive(specs / "archive" / "evidence-handoff-a2a-ledger-design_v2.md")  # still at root
    assert resolves_with_archive(moved_bundle_file)  # a whole folder moved into sources/archive/


def test_a_genuinely_missing_target_is_still_rejected() -> None:
    specs = DOCS_ROOT / "superpowers" / "specs"

    assert not resolves_with_archive(specs / "never-existed.md")
    assert not resolves_with_archive(specs / "archive" / "never-existed.md")
    assert not resolves_with_archive(Path(DOCS_ROOT.parent / "reports" / "archive" / "never-existed.md"))


def test_links_resolve_for_moved_targets_and_from_moved_documents() -> None:
    backlog = doc_path(BACKLOG)
    archived_runbook = DOCS_ROOT / "runbooks" / "archive" / "plan-9-6-phase-c-operator-path.md"

    assert link_resolves(backlog, "../specs/" + ARCHIVED_SPEC)
    # Written when the runbook sat one level higher; the link text was never rewritten.
    assert link_resolves(archived_runbook, "../../reports/plan-9-7-manual-e2e-evidence.md")
    assert not link_resolves(backlog, "../specs/never-existed.md")
    assert not link_resolves(archived_runbook, "../../reports/never-existed.md")
