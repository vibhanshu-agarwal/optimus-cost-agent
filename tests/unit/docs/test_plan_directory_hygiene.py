"""Structural invariants for the implementation-plan directory."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from tools.doc_paths import link_resolves, resolves_with_archive

REPO_ROOT = Path(__file__).resolve().parents[3]
PLANS_ROOT = REPO_ROOT / "docs/superpowers/plans"
ARCHIVE_ROOT = PLANS_ROOT / "archive"
BACKLOG = PLANS_ROOT / "2026-07-23-consolidated-deferred-followups-backlog.md"
HARDENING_MASTERPLAN = PLANS_ROOT / "hardening-runtime-quality-masterplan.md"

ROOT_GOVERNANCE_DOCUMENTS = {
    "README.md",
    "2026-07-01-phase-1-roadmap.md",
    "2026-07-23-consolidated-deferred-followups-backlog.md",
    "2026-07-25-plan-11-v1-milestone-charter.md",
    "hardening-runtime-quality-masterplan.md",
}

LIVE_REGISTRY_ROW = re.compile(
    r"^\| \[[^]]+\]\((?P<path>[^)]+\.md)\) "
    r"\| `(?P<state>Active|Blocked)` \| `(?P<owner>[^`]+)` \| (?P<next_gate>.+) \|$"
)
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\((?P<target>[^)]+)\)")
PLAN_LEVEL_STATUS = re.compile(r"(?mi)^\*\*Status:\*\*|^Status:")
# Exact (document, raw link text) pairs allowed to stay broken. Every entry
# here must be a real, individually justified case -- never a directory- or
# document-wide bypass.

# Pre-existing, unrelated to PR #193's archive move. Verified against `main`
# before the move: these 4 links already 404'd at their pre-move location (a
# plain authoring mistake in a frozen 2026-07-10 plan, e.g. a missing
# `../../../` before `reports/...`), so the move did not create them and
# PR #193's document-repair lane does not claim to fix them.
PRE_EXISTING_STALE_LINK_EXEMPTIONS: set[tuple[str, str]] = {
    (
        "docs/superpowers/plans/archive/2026-07-10-plan-9-6-live-signoff-execution.md",
        "reports/plan-9-6-phase-a-evidence.md",
    ),
    (
        "docs/superpowers/plans/archive/2026-07-10-plan-9-6-live-signoff-execution.md",
        "reports/plan-9-6-phase-b-evidence.md",
    ),
    (
        "docs/superpowers/plans/archive/2026-07-10-plan-9-6-live-signoff-execution.md",
        "reports/plan-9-6-phase-d-evidence.md",
    ),
    (
        "docs/superpowers/plans/archive/2026-07-10-plan-9-6-live-signoff-execution.md",
        "2026-07-10-plan-9-6-phase-c-operator-runbook.md",
    ),
}

STALE_LINK_EXEMPTIONS = PRE_EXISTING_STALE_LINK_EXEMPTIONS
# Reviewer checkpoint logs are deliberately gitignored (AGENTS.md), so references to them never resolve.
GITIGNORED_DOC_SUFFIXES = ("-review-checkpoints.md",)
# Exact (document file name, named path) pairs in frozen archived plans that name a document
# which never existed at that path: a spec cited under plans/, a runbook that became
# docs/runbooks/plan-9-6-phase-c-operator-path.md, an amendment never committed, and an
# uncommitted draft. Keyed by file name so a later archive move does not invalidate them.
DANGLING_TEXT_REFERENCE_EXEMPTIONS = {
    (
        "2026-07-14-plan-9-9-operator-packaging-and-credential-diagnostics.md",
        "docs/superpowers/plans/2026-07-10-plan-9-6-phase-c-operator-runbook.md",
    ),
    (
        "2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md",
        "docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md",
    ),
    (
        "2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md",
        "docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md",
    ),
    (
        "evidence-handoff-risk-bearing-slice-implementation_v2.md",
        "docs/superpowers/plans/2026-08-09-evidence-handoff-durable-signing-key-custody-amendment.md",
    ),
    (
        "2026-07-04-usage-accounting-evidence-ledger-observability.md",
        "docs/superpowers/plans/drafts/2026-07-04-plan-7-working-notes.md",
    ),
}
# A repository path to a document, written as plain text rather than a Markdown link (for
# example "Plan file: docs/superpowers/plans/X.md"). Frozen documents keep such text when the
# document they name later moves into archive/, so it is checked with archive tolerance.
REPOSITORY_DOC_PATH = re.compile(
    r"docs/superpowers/(?:plans|specs|reviews|reports)/(?P<target>[A-Za-z0-9_./-]+\.md)"
)


def _tracked_repository_files() -> tuple[Path, ...]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split("\0")
    return tuple(REPO_ROOT / relative_path for relative_path in tracked if relative_path)


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


def _hardening_child_plan_rows() -> list[dict[str, str | None]]:
    text = HARDENING_MASTERPLAN.read_text(encoding="utf-8")
    section = re.search(
        r"^## Child-plan status board\n(?P<body>.*?)(?=^## )",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert section is not None, "the hardening masterplan must own a child-plan status board"

    rows: list[dict[str, str | None]] = []
    allowed_statuses = {"Not drafted", "In review", "Ready", "Active", "Blocked", "Complete"}
    plain_plan = re.compile(r"^`(?P<filename>hardening-[a-z0-9-]+(?:_v[0-9]+)?\.md)`$")
    linked_plan = re.compile(
        r"^\[[^]]+\]\((?P<target>(?:archive/)?hardening-[a-z0-9-]+(?:_v[0-9]+)?\.md)\)$"
    )
    for line in section.group("body").splitlines():
        if not line.startswith("| `HARDENING-TRACK-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 5, f"malformed hardening child-plan row: {line}"
        track = cells[0].strip("`")
        status = cells[2].strip("`")
        assert status in allowed_statuses, f"unknown hardening child-plan status: {status}"

        plain_match = plain_plan.fullmatch(cells[1])
        link_match = linked_plan.fullmatch(cells[1])
        assert (plain_match is None) != (link_match is None), f"invalid hardening plan cell: {cells[1]}"
        filename = plain_match.group("filename") if plain_match else Path(link_match.group("target")).name
        link_target = link_match.group("target") if link_match else None
        if status == "Not drafted":
            assert link_target is None, "untracked hardening child plans must not be links"
        elif status == "Complete":
            assert link_target is not None and link_target.startswith("archive/")
        else:
            assert link_target == filename, "live hardening child plans must link to the plan root"
        rows.append(
            {
                "track": track,
                "filename": filename,
                "status": status,
                "link_target": link_target,
            }
        )
    return rows


def test_plan_root_contains_only_governance_and_registered_live_plans() -> None:
    registry_paths = [match.group("path") for match in _live_registry_rows()]
    assert len(registry_paths) == len(set(registry_paths)), "live plans must be registered exactly once"
    assert all("/" not in path and "\\" not in path for path in registry_paths)

    hardening_rows = _hardening_child_plan_rows()
    hardening_root_paths = {
        str(row["filename"])
        for row in hardening_rows
        if row["status"] in {"In review", "Ready", "Active", "Blocked"}
    }
    assert hardening_root_paths.isdisjoint(registry_paths), (
        "hardening child-plan status belongs to the masterplan, not the backlog registry"
    )

    actual_root_files = {path.name for path in PLANS_ROOT.glob("*.md")}
    expected_root_files = ROOT_GOVERNANCE_DOCUMENTS | set(registry_paths) | hardening_root_paths
    assert actual_root_files == expected_root_files, (
        "unowned root plan file(s): "
        f"extra={sorted(actual_root_files - expected_root_files)!r} "
        f"missing={sorted(expected_root_files - actual_root_files)!r}"
    )


def test_hardening_masterplan_owns_exactly_fifteen_child_plan_statuses() -> None:
    rows = _hardening_child_plan_rows()

    assert len(rows) == 15
    assert len({row["track"] for row in rows}) == 15
    assert len({row["filename"] for row in rows}) == 15
    active_rows = [row for row in rows if row["status"] == "Active"]
    assert {row["track"] for row in active_rows} == {"HARDENING-TRACK-CI-GUARDRAILS"}
    assert all(row["link_target"] == row["filename"] for row in active_rows)
    not_drafted_rows = [row for row in rows if row["status"] == "Not drafted"]
    assert len(not_drafted_rows) == 14
    assert all(row["link_target"] is None for row in not_drafted_rows)

    text = HARDENING_MASTERPLAN.read_text(encoding="utf-8")
    assert PLAN_LEVEL_STATUS.search(text) is None

    for row in rows:
        link_target = row["link_target"]
        if link_target is None:
            continue
        child_text = (PLANS_ROOT / str(link_target)).read_text(encoding="utf-8")
        assert PLAN_LEVEL_STATUS.search(child_text) is None, (
            f"hardening child plan {row['track']} must not declare its own status"
        )


def test_plan_archive_is_flat_and_contains_no_registered_live_plan() -> None:
    registry_paths = {match.group("path") for match in _live_registry_rows()}
    assert ARCHIVE_ROOT.is_dir()
    assert not [path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()]

    archived_names = {path.name for path in ARCHIVE_ROOT.glob("*.md")}
    assert archived_names
    assert archived_names.isdisjoint(registry_paths)
    completed_hardening = {
        str(row["filename"])
        for row in _hardening_child_plan_rows()
        if row["status"] == "Complete"
    }
    assert completed_hardening <= archived_names


def test_separately_named_amendments_cannot_be_live_root_plans() -> None:
    root_plan_names = {
        path.name
        for path in PLANS_ROOT.glob("*.md")
        if path.name not in ROOT_GOVERNANCE_DOCUMENTS
    }
    assert not {name for name in root_plan_names if "amendment" in name.lower()}


def test_markdown_link_regex_still_matches_after_backtick_stripping_empties_the_label() -> None:
    """`[`P11-FU-11`](broken.md)` is a real, common style in this repo's docs.
    Inline-code stripping (used to avoid false positives from code examples)
    removes the backticked label, leaving `[](broken.md)` -- a link with an
    empty label is still a real, clickable link, and must still be matched."""
    text = re.sub(r"`[^`\n]*`", "", "See [`P11-FU-11`](broken.md) for detail.")
    assert text == "See [](broken.md) for detail."

    matches = list(MARKDOWN_LINK.finditer(text))
    assert [m.group("target") for m in matches] == ["broken.md"]


def test_relative_markdown_links_resolve_except_registered_stale_links() -> None:
    """Every relative Markdown link resolves, allowing for a target that has since moved
    between its folder root and archive/ (frozen documents are never edited to follow it)."""
    used_exemptions: set[tuple[str, str]] = set()
    for document in _tracked_repository_files():
        if document.suffix != ".md":
            continue
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"```.*?```|~~~.*?~~~", "", text, flags=re.DOTALL)
        text = re.sub(r"`[^`\n]*`", "", text)
        relative_document = document.relative_to(REPO_ROOT).as_posix()
        for match in MARKDOWN_LINK.finditer(text):
            raw_target = match.group("target")
            target = urlsplit(raw_target)
            if target.scheme or not target.path:
                continue
            if link_resolves(document, target.path):
                continue
            exemption = (relative_document, raw_target)
            assert exemption in STALE_LINK_EXEMPTIONS, (
                f"broken relative link in {relative_document}: {raw_target}"
            )
            used_exemptions.add(exemption)

    assert used_exemptions == STALE_LINK_EXEMPTIONS, (
        "stale-link exemptions must be exact; remove exemptions for links that now resolve"
    )


def test_repository_document_paths_in_text_resolve() -> None:
    """Plain-text repository paths to superpowers documents (inside archive/ too) resolve,
    allowing for a document that has since moved between its folder root and archive/."""
    used_exemptions: set[tuple[str, str]] = set()
    for document in _tracked_repository_files():
        if not document.is_file() or "tests" in document.relative_to(REPO_ROOT).parts:
            continue
        try:
            text = document.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in REPOSITORY_DOC_PATH.finditer(text):
            name = Path(match.group("target")).name
            if name.startswith("YYYY-MM-DD-") or name.endswith(GITIGNORED_DOC_SUFFIXES):
                continue
            if _resolves(REPO_ROOT / match.group(0)):
                continue
            exemption = (document.name, match.group(0))
            assert exemption in DANGLING_TEXT_REFERENCE_EXEMPTIONS, (
                f"{document.relative_to(REPO_ROOT).as_posix()} names a missing document: {match.group(0)}"
            )
            used_exemptions.add(exemption)

    assert used_exemptions == DANGLING_TEXT_REFERENCE_EXEMPTIONS, (
        "dangling-reference exemptions must be exact; remove exemptions whose path now resolves"
    )


def _resolves(path: Path) -> bool:
    return resolves_with_archive(path.resolve())
