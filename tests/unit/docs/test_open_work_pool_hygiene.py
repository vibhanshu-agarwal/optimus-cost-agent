"""Repository invariants for the Optimus and evidence/handoff open-work pools."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OPTIMUS_POOL = REPO_ROOT / "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"
PRODUCT_POOL = REPO_ROOT / "docs/superpowers/plans/evidence-handoff-open-work-pool.md"

PRODUCT_FEATURE_IDS = frozenset(
    {
        "EVIDENCE-HANDOFF-FEAT-REDACTION-GATE",
        "EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR",
        "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER",
        "EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD",
    }
)
PRODUCT_OWNED_DOCS = frozenset(
    {
        "docs/superpowers/specs/evidence-handoff-redaction-gate-design.md",
        "docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md",
    }
)

FEATURE_ID_BODY = r"(?:[A-Z][A-Z0-9]*-)*FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*"
FEATURE_ID_RE = re.compile(rf"(?<![A-Z0-9-]){FEATURE_ID_BODY}(?![A-Z0-9-])")
FEATURE_ROW_RE = re.compile(rf"^\|\s*`(?P<identity>{FEATURE_ID_BODY})`\s*\|", re.MULTILINE)
PLAN_NUMBER_RE = re.compile(r"\bPlan [0-9]|\bplan-[0-9]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _feature_rows(text: str) -> Counter[str]:
    return Counter(match.group("identity") for match in FEATURE_ROW_RE.finditer(text))


def test_product_features_have_exactly_one_pool_owner() -> None:
    optimus_rows = _feature_rows(_read(OPTIMUS_POOL))
    product_rows = _feature_rows(_read(PRODUCT_POOL))

    assert not (optimus_rows.keys() & product_rows.keys())
    assert all(optimus_rows[feature_id] + product_rows[feature_id] == 1 for feature_id in PRODUCT_FEATURE_IDS)
    assert PRODUCT_FEATURE_IDS <= product_rows.keys()


def test_new_pool_has_no_scheduling_plan_numbers() -> None:
    assert PLAN_NUMBER_RE.search(_read(PRODUCT_POOL)) is None


def test_new_pool_links_only_to_explicitly_product_owned_documents() -> None:
    pool_text = _read(PRODUCT_POOL)
    ownership_section = pool_text.split("## Product-owned documents temporarily hosted in Optimus", 1)[1].split("\n## ", 1)[0]
    listed_docs = frozenset(re.findall(r"`(docs/superpowers/(?:plans|specs)/[^`]+\.md)`", ownership_section))
    linked_docs: set[str] = set()

    for match in MARKDOWN_LINK_RE.finditer(pool_text):
        target = match.group("target").split("#", 1)[0]
        if not target or "://" in target:
            continue
        resolved = (PRODUCT_POOL.parent / target).resolve()
        linked_docs.add(resolved.relative_to(REPO_ROOT).as_posix())

    assert listed_docs == PRODUCT_OWNED_DOCS
    assert linked_docs <= PRODUCT_OWNED_DOCS
    assert all((REPO_ROOT / path).is_file() for path in PRODUCT_OWNED_DOCS)


def test_optimus_dependency_references_resolve_to_product_pool_without_status_custody() -> None:
    optimus_text = _read(OPTIMUS_POOL)
    product_rows = _feature_rows(_read(PRODUCT_POOL))
    dependency_clauses = tuple(line.split("Dependency:", 1)[1] for line in optimus_text.splitlines() if "Dependency:" in line)
    dependency_ids: set[str] = set()

    for clause in dependency_clauses:
        referenced_ids = set(FEATURE_ID_RE.findall(clause))
        if not (referenced_ids & product_rows.keys()):
            continue
        assert "(evidence-handoff-open-work-pool.md)" in clause
        assert re.search(r"\b(?:state|status|ratified|unscheduled|blocked|closed)\b", clause, re.IGNORECASE) is None
        dependency_ids.update(referenced_ids)

    assert dependency_ids == {"EVIDENCE-HANDOFF-FEAT-REDACTION-GATE"}
    assert dependency_ids <= product_rows.keys()


def test_product_checkpoint_log_location_remains_gitignored() -> None:
    checkpoint = "docs/superpowers/reviews/evidence-handoff-review-checkpoints.md"
    result = subprocess.run(
        ["git", "check-ignore", "--quiet", "--", checkpoint],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
