"""Structural invariants for the implementation-plan directory."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
PLANS_ROOT = REPO_ROOT / "docs/superpowers/plans"
ARCHIVE_ROOT = PLANS_ROOT / "archive"
BACKLOG = PLANS_ROOT / "2026-07-23-consolidated-deferred-followups-backlog.md"

ROOT_GOVERNANCE_DOCUMENTS = {
    "README.md",
    "2026-07-01-phase-1-roadmap.md",
    "2026-07-23-consolidated-deferred-followups-backlog.md",
    "2026-07-25-plan-11-v1-milestone-charter.md",
}

LIVE_REGISTRY_ROW = re.compile(
    r"^\| \[[^]]+\]\((?P<path>[^)]+\.md)\) "
    r"\| `(?P<state>Active|Blocked)` \| `(?P<owner>[^`]+)` \| (?P<next_gate>.+) \|$"
)
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\((?P<target>[^)]+)\)")
REPOSITORY_PLAN_PATH = re.compile(
    r"docs/superpowers/plans/(?P<target>[A-Za-z0-9_./-]+\.md)"
)


def _live_registry_rows() -> list[re.Match[str]]:
    text = BACKLOG.read_text(encoding="utf-8")
    section = re.search(
        r"^## Live implementation plan registry\n(?P<body>.*?)(?=^## )",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert section is not None, "the consolidated backlog must own the live-plan registry"
    rows = [
        match
        for line in section.group("body").splitlines()
        if (match := LIVE_REGISTRY_ROW.fullmatch(line)) is not None
    ]
    assert rows, "the live-plan registry must contain at least one Active or Blocked plan"
    return rows


def test_plan_root_contains_only_governance_and_registered_live_plans() -> None:
    registry_paths = [match.group("path") for match in _live_registry_rows()]
    assert len(registry_paths) == len(set(registry_paths)), "live plans must be registered exactly once"
    assert all("/" not in path and "\\" not in path for path in registry_paths)

    actual_root_files = {path.name for path in PLANS_ROOT.glob("*.md")}
    assert actual_root_files == ROOT_GOVERNANCE_DOCUMENTS | set(registry_paths)


def test_plan_archive_is_flat_and_contains_no_registered_live_plan() -> None:
    registry_paths = {match.group("path") for match in _live_registry_rows()}
    assert ARCHIVE_ROOT.is_dir()
    assert not [path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()]

    archived_names = {path.name for path in ARCHIVE_ROOT.glob("*.md")}
    assert archived_names
    assert archived_names.isdisjoint(registry_paths)


def test_separately_named_amendments_cannot_be_live_root_plans() -> None:
    root_plan_names = {
        path.name
        for path in PLANS_ROOT.glob("*.md")
        if path.name not in ROOT_GOVERNANCE_DOCUMENTS
    }
    assert not {name for name in root_plan_names if "amendment" in name.lower()}


def test_rewritten_archive_links_outside_the_archive_resolve() -> None:
    for document in REPO_ROOT.rglob("*.md"):
        if ARCHIVE_ROOT in document.parents or ".venv" in document.parts:
            continue
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```|~~~.*?~~~", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`\n]*`", "", text)
        for match in MARKDOWN_LINK.finditer(text):
            target = urlsplit(match.group("target"))
            if target.scheme or "archive/" not in target.path:
                continue
            resolved = (document.parent / target.path).resolve()
            assert resolved.exists(), f"broken archive link in {document}: {target.path}"


def test_repository_relative_plan_paths_resolve_or_have_an_archived_successor() -> None:
    for document in REPO_ROOT.rglob("*"):
        if (
            not document.is_file()
            or ARCHIVE_ROOT in document.parents
            or ".git" in document.parts
            or ".venv" in document.parts
            or "tests" in document.parts
        ):
            continue
        try:
            text = document.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in REPOSITORY_PLAN_PATH.finditer(text):
            if match.group("target").startswith("YYYY-MM-DD-"):
                continue
            target = PLANS_ROOT / match.group("target")
            archived_target = ARCHIVE_ROOT / Path(match.group("target")).name
            assert target.is_file() or archived_target.is_file(), (
                f"unknown plan path in {document}: {match.group(0)}"
            )
