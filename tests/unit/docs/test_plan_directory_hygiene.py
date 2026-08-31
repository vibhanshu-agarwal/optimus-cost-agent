"""Structural invariants for the implementation-plan directory."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

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
REPOSITORY_PLAN_PATH = re.compile(
    r"docs/superpowers/plans/(?P<target>[A-Za-z0-9_./-]+\.md)"
)
FROZEN_REFERENCE_EXEMPTIONS = {
    (
        "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md",
        "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v2.md",
    ),
    (
        "docs/superpowers/plans/2026-08-18-plan-11-23-p11-fu-20-client-mcp-runtime-composition.md",
        "docs/superpowers/plans/2026-08-17-plan-11-20-p11-fu-20-client-mcp-one-call-approval.md",
    ),
    *{
        (
            "docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe_v6.md",
            f"docs/superpowers/plans/2026-08-18-plan-11-24-zed-guided-session-load-probe{suffix}.md",
        )
        for suffix in ("", "_v2", "_v3", "_v4", "_v5")
    },
    (
        "docs/superpowers/plans/evidence-handoff-evidence-collector-implementation.md",
        "docs/superpowers/plans/evidence-handoff-open-work-pool.md",
    ),
    (
        "docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md",
        "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md",
    ),
    (
        "docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md",
        "docs/superpowers/plans/2026-07-07-plan-9-6-live-verification-and-lld-alignment.md",
    ),
    (
        "reports/plan-11-20-p11-fu-20-release.md",
        "docs/superpowers/plans/2026-08-06-p11-fu-9-client-supplied-acp-mcp-servers-implementation.md",
    ),
    (
        "reports/plan-11-21-p11-5-fu-1-release.md",
        "docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md",
    ),
    *{
        ("reports/plan-11-7-server-custody-artifact-manifest.json", target)
        for target in (
            "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md",
        )
    },
    *{
        (
            "reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/document-freshness-audit.json",
            target,
        )
        for target in (
            "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md",
            "docs/superpowers/plans/evidence-handoff-open-work-pool.md",
        )
    },
    *{
        (
            "reports/plan-11-7-server-custody-artifacts/amendments/origin-a-fixture-v2/trigger-chain.json",
            target,
        )
        for target in (
            "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md",
        )
    },
    (
        "reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/assert-prompt-retry-preflight-signature-supersession-note.md",
        "docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
    ),
    *{
        (
            "reports/plan-11-7-server-custody-artifacts/amendments/retry-preflight-gate/task0-checkpoint.json",
            target,
        )
        for target in (
            "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md",
            "docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
        )
    },
    *{
        ("reports/plan-11-7-server-custody-artifacts/trigger-chain.json", target)
        for target in (
            "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md",
            "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md",
        )
    },
    # Historical review/approval records under docs/superpowers/reviews/, restored to their
    # pre-archival-move committed bytes (PR #193 review ruling 2026-08-28): these records stay
    # historical evidence and are not edited to repair a path string, even when the plan they
    # cite has since moved into archive/. This differs from a "frozen provenance" plan/spec
    # reference above only in scope of the rule -- the mechanism is identical.
    (
        "docs/superpowers/reviews/2026-07-03-plan-5-architect-review.md",
        "docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-03-plan-5-security-review.md",
        "docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-04-pr-13-permission-engine-review.md",
        "docs/superpowers/plans/2026-07-03-permission-engine-pre-tool-guard-shell-safety.md",
    ),
    *{
        (
            f"docs/superpowers/reviews/2026-07-04-plan-6-5-architect-review{suffix}.md",
            "docs/superpowers/plans/2026-07-04-plan-6-5-guardrail-hardening-mcp-runtime-trust.md",
        )
        for suffix in ("", "-round-2")
    },
    *{
        (
            f"docs/superpowers/reviews/2026-07-04-plan-6-security-review{suffix}.md",
            "docs/superpowers/plans/2026-07-04-prompt-injection-mcp-trust-ci-guardrail-parity.md",
        )
        for suffix in ("", "-round-2")
    },
    *{
        (
            f"docs/superpowers/reviews/2026-07-04-plan-7-architect-review{suffix}.md",
            "docs/superpowers/plans/2026-07-04-usage-accounting-evidence-ledger-observability.md",
        )
        for suffix in ("", "-round-2")
    },
    (
        "docs/superpowers/reviews/2026-07-15-plan-9-96-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust.md",
    ),
    *{
        (
            f"docs/superpowers/reviews/2026-07-18-plan-9-98-implementation-plan-approval{suffix}.md",
            "docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md",
        )
        for suffix in ("", "-v2", "-v3", "-v4", "-v5", "-v6")
    },
    (
        "docs/superpowers/reviews/2026-07-19-plan-9-98-implementation-plan-approval-v7.md",
        "docs/superpowers/plans/2026-07-18-plan-9-98-real-acpx-session-evidence.md",
    ),
    *{
        (
            f"docs/superpowers/reviews/2026-07-19-plan-9-98-fu-1-implementation-plan-approval{suffix}.md",
            "docs/superpowers/plans/2026-07-19-plan-9-98-fu-1-workspace-identity-linux-ci.md",
        )
        for suffix in ("", "-v2", "-v3")
    },
    (
        "docs/superpowers/reviews/2026-07-19-plan-9-98-fu-2-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-19-plan-9-98-fu-2-approval-time-runtime-bootstrap.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-22-plan-9-98-fu-3-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-22-plan-9-98-fu-3-posix-runtime-root-tests.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-22-plan-9-99-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-23-plan-10-1-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-23-plan-10-2-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md",
    ),
    (
        "docs/superpowers/reviews/2026-07-24-plan-10-3-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md",
    ),
    *{
        (
            f"docs/superpowers/reviews/2026-07-25-plan-11-1-implementation-plan-approval{suffix}.md",
            "docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md",
        )
        for suffix in ("", "-v2")
    },
    (
        "docs/superpowers/reviews/2026-07-26-plan-11-2-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md",
    ),
    *{
        (
            "docs/superpowers/reviews/2026-07-27-plan-11-2-implementation-plan-approval-v2.md",
            target,
        )
        for target in (
            "docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md",
            "docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md",
        )
    },
    *{
        (
            "docs/superpowers/reviews/2026-07-27-plan-11-3-implementation-plan-approval.md",
            target,
        )
        for target in (
            "docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md",
            "docs/superpowers/plans/2026-07-27-plan-11-3-real-provider-adapters.md",
        )
    },
    (
        "docs/superpowers/reviews/2026-07-29-plan-11-6-implementation-plan-approval.md",
        "docs/superpowers/plans/2026-07-29-plan-11-6-p11-5-fu-2-local-startup-consolidation.md",
    ),
    *{
        (
            "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md",
            f"docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure{suffix}.md",
        )
        for suffix in ("", "_v2", "_v3")
    },
    (
        "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md",
        "docs/superpowers/plans/evidence-handoff-open-work-pool.md",
    ),
}


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
    assert {row["status"] for row in rows} == {"Not drafted"}
    assert all(row["link_target"] is None for row in rows)

    text = HARDENING_MASTERPLAN.read_text(encoding="utf-8")
    assert re.search(r"(?mi)^\*\*Status:\*\*|^Status:", text) is None


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
            resolved = (document.parent / target.path).resolve()
            if resolved.exists():
                continue
            exemption = (relative_document, raw_target)
            assert exemption in STALE_LINK_EXEMPTIONS, (
                f"broken relative link in {relative_document}: {raw_target}"
            )
            used_exemptions.add(exemption)

    assert used_exemptions == STALE_LINK_EXEMPTIONS, (
        "stale-link exemptions must be exact; remove exemptions for links that now resolve"
    )


def test_repository_relative_plan_paths_are_repaired_except_in_frozen_provenance() -> None:
    # NOTE: the ARCHIVE_ROOT skip below is deliberate, not an oversight carried
    # over from before the archive move. This function's REPOSITORY_PLAN_PATH
    # regex matches the literal substring anywhere in raw text (not just inside
    # markdown link syntax), so removing the skip surfaces every archived
    # document's own un-prefixed self-reference and sibling cross-reference
    # (e.g. a "Plan file: docs/superpowers/plans/X.md" header) -- 159 such
    # hits across 62 distinct archived documents as of PR #193, none of them
    # navigable dead links (that class is covered, including archive/, by
    # test_relative_markdown_links_resolve_except_registered_stale_links
    # above). Repairing or exempting that class at the necessary per-instance
    # granularity is a separate, much larger effort than the 4-document /
    # 12-link repair this PR's document-repair lane is scoped to, and is
    # intentionally left out of scope here pending an explicit ruling.
    used_exemptions: set[tuple[str, str]] = set()
    for document in _tracked_repository_files():
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
            if target.is_file():
                continue
            relative_document = document.relative_to(REPO_ROOT).as_posix()
            exemption = (relative_document, match.group(0))
            assert exemption in FROZEN_REFERENCE_EXEMPTIONS, (
                f"stale plan path in mutable document {document}: {match.group(0)}"
            )
            used_exemptions.add(exemption)
            assert archived_target.is_file(), f"missing archived target for {match.group(0)}"

    assert used_exemptions == FROZEN_REFERENCE_EXEMPTIONS, (
        "frozen-reference exemptions must be exact; remove exemptions that no longer preserve "
        "a historical plan path"
    )
