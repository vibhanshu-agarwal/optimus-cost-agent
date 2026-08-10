"""Repository invariants for the Optimus and evidence/handoff open-work pools."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[3]
OPTIMUS_POOL = REPO_ROOT / "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"
PRODUCT_POOL = REPO_ROOT / "docs/superpowers/plans/evidence-handoff-open-work-pool.md"
A2A_LEDGER_DESIGN = REPO_ROOT / "docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md"
A2A_LEDGER_IMPLEMENTATION_PLAN = REPO_ROOT / "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md"
PLANS_ROOT = REPO_ROOT / "docs/superpowers/plans"

PRODUCT_FEATURE_IDS = frozenset(
    {
        "EVIDENCE-HANDOFF-FEAT-REDACTION-GATE",
        "EVIDENCE-HANDOFF-FEAT-EVIDENCE-COLLECTOR",
        "EVIDENCE-HANDOFF-FEAT-ZED-RENDER-OBSERVATION",
        "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER",
        "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH",
        "EVIDENCE-HANDOFF-FEAT-APPROVAL-RECORD",
        "EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL",
        "EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE",
        "EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY",
    }
)
PRODUCT_OWNED_DOCS = frozenset(
    {
        "docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md",
        "docs/superpowers/specs/evidence-handoff-evidence-collector-design.md",
        "docs/superpowers/specs/evidence-handoff-redaction-gate-design.md",
        "docs/superpowers/specs/evidence-handoff-zed-render-observation-design.md",
        "docs/superpowers/plans/evidence-handoff-evidence-collector-implementation.md",
        "docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md",
        "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md",
        "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation_v2.md",
    }
)

FEATURE_ID_BODY = r"(?:[A-Z][A-Z0-9]*-)*FEAT-[A-Z0-9]+(?:-[A-Z0-9]+)*"
FEATURE_ID_RE = re.compile(rf"(?<![A-Z0-9-]){FEATURE_ID_BODY}(?![A-Z0-9-])")
FEATURE_ROW_RE = re.compile(rf"^\|\s*`(?P<identity>{FEATURE_ID_BODY})`\s*\|", re.MULTILINE)
PLAN_NUMBER_RE = re.compile(r"\bPlan [0-9]|\bplan-[0-9]")
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")
FU_ID_BODY = r"P\d+(?:\.\d+)*-FU-\d+"
SECTION_HEADING_RE = re.compile(r"^(?P<level>##|###) (?P<title>.+)$", re.MULTILINE)
FU_HEADING_RE = re.compile(rf"^(?P<identity>{FU_ID_BODY}): (?P<title>.+)$")
STATUS_LINE_RE = re.compile(r"^\*\*Status:\*\*\s*(?P<value>.+)$", re.MULTILINE)
FIXED_STATUS_RE = re.compile(
    r"^(?P<token>Open|Partially implemented|Closed|Reviewed disposition)[.:](?:\s|$)"
)
PROMOTED_STATUS_RE = re.compile(
    r"^(?P<token>Promoted -> \[[^\]]+\]\((?P<target>[^)]+)\))[.:](?:\s|$)"
)
FU_INDEX_ROW_RE = re.compile(
    rf"^\|\s*`(?P<identity>{FU_ID_BODY})`\s*\|\s*(?P<item>[^|]+?)\s*\|"
    r"\s*(?P<status>.*?)\s*\|\s*(?P<owner>.*?)\s*\|\s*(?P<evidence>.*?)\s*\|\s*$",
    re.MULTILINE,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _feature_rows(text: str) -> Counter[str]:
    return Counter(match.group("identity") for match in FEATURE_ROW_RE.finditer(text))


def _entry_sections(text: str) -> dict[str, str]:
    headings = tuple(SECTION_HEADING_RE.finditer(text))
    entries: dict[str, str] = {}
    for index, heading in enumerate(headings):
        if heading.group("level") != "###":
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        title = heading.group("title")
        assert title not in entries
        entries[title] = text[heading.end() : end]
    return entries


def _status_token(section_body: str) -> str:
    matches = tuple(STATUS_LINE_RE.finditer(section_body))
    assert len(matches) == 1
    value = matches[0].group("value").strip()
    promoted = PROMOTED_STATUS_RE.match(value)
    if promoted is not None:
        return promoted.group("token")
    fixed = FIXED_STATUS_RE.match(value)
    assert fixed is not None, value
    return fixed.group("token")


def _fu_index_rows(text: str) -> dict[str, tuple[str, str]]:
    section = text.split("## Follow-up status index", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, tuple[str, str]] = {}
    for match in FU_INDEX_ROW_RE.finditer(section):
        identity = match.group("identity")
        assert identity not in rows
        rows[identity] = (match.group("item").strip(), match.group("status").strip())
    return rows


def _relative_link_targets(text: str) -> tuple[str, ...]:
    targets: list[str] = []
    for match in MARKDOWN_LINK_RE.finditer(text):
        target = match.group("target").strip()
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("#"):
            continue
        assert parsed.path
        targets.append(parsed.path)
    return tuple(targets)


def _feature_row(text: str, identity: str) -> str:
    prefix = f"| `{identity}` |"
    return next(line for line in text.splitlines() if line.startswith(prefix))


def test_product_features_have_exactly_one_pool_owner() -> None:
    optimus_rows = _feature_rows(_read(OPTIMUS_POOL))
    product_rows = _feature_rows(_read(PRODUCT_POOL))

    assert not (optimus_rows.keys() & product_rows.keys())
    assert all(optimus_rows[feature_id] + product_rows[feature_id] == 1 for feature_id in PRODUCT_FEATURE_IDS)
    assert PRODUCT_FEATURE_IDS <= product_rows.keys()


def test_a2a_ledger_reachability_blocker_is_resolved_and_design_is_owned() -> None:
    row = _feature_row(_read(PRODUCT_POOL), "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER")

    assert "The cross-agent reachability blocker is resolved" in row
    assert "Blocked on the cross-agent localhost-TCP reachability investigation" not in row
    assert "[Design](../specs/evidence-handoff-a2a-ledger-design.md)" in row
    assert "[v2 plan](evidence-handoff-risk-bearing-slice-implementation_v2.md)" in row
    assert "[v1 plan](evidence-handoff-risk-bearing-slice-implementation.md)" in row
    assert A2A_LEDGER_DESIGN.is_file()
    assert A2A_LEDGER_IMPLEMENTATION_PLAN.is_file()
    assert (
        REPO_ROOT / "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation_v2.md"
    ).is_file()
    assert PLAN_NUMBER_RE.search(_read(A2A_LEDGER_DESIGN)) is None


def test_a2a_ledger_plan_freezes_ordered_risk_slice_scope() -> None:
    plan = _read(A2A_LEDGER_IMPLEMENTATION_PLAN)
    normalized = " ".join(plan.split())

    assert "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER" in plan
    assert "Ordered Subplan A: Persistence, Lifecycle, Integrity, and Recovery" in plan
    assert "Ordered Subplan B: Streamable HTTP Service, Identity, Security, and Redaction" in plan
    assert "Ordered Subplan C: Recipient Delivery, Capabilities, Observability, and Three-Agent Evidence" in plan
    assert "Ledger protocol completion" in plan
    assert "Evidence bridge" in plan
    assert "Operations and extraction" in plan
    assert "Real Claude Code, Codex, and Cursor" in plan
    assert "After an integrity latch, explicitly disable the feature and, in a separate run, make PostgreSQL unavailable" in normalized
    assert PLAN_NUMBER_RE.search(plan) is None


def test_a2a_ledger_freezes_recipient_visibility_in_the_first_slice() -> None:
    design = _read(A2A_LEDGER_DESIGN)
    normalized = " ".join(design.split())
    first_slice = design.split("### Risk-bearing vertical slice", 1)[1].split("\n### ", 1)[0]
    protocol_completion = design.split("### Ledger protocol completion", 1)[1].split("\n### ", 1)[0]

    assert "### Frozen v1 recipient visibility" in design
    assert "must name at least one registered recipient" in normalized
    assert "if and only if" in normalized
    assert "cannot reinterpret an existing entry's visibility" in design
    assert "Frozen v1 recipient visibility" in first_slice
    assert "recipient visibility" not in protocol_completion


def test_a2a_ledger_integrity_detection_is_a_first_slice_contract() -> None:
    design = _read(A2A_LEDGER_DESIGN)
    normalized = " ".join(design.split())
    first_slice = design.split("### Risk-bearing vertical slice", 1)[1].split("\n### ", 1)[0]

    assert "`ledger_instance_id`" in design
    assert "`prev_content_sha256`" in design
    assert "`sequence` has a database `UNIQUE NOT NULL` constraint" in normalized
    assert "unfiltered global sequence range" in normalized
    assert "before recipient filtering" in normalized
    assert "Visible sequence gaps are expected" in normalized
    assert "Chain verification is service-side" in normalized
    assert "Continuous integrity verification" in first_slice


def test_a2a_ledger_integrity_failure_is_loud_latched_and_non_retryable() -> None:
    design = _read(A2A_LEDGER_DESIGN)
    normalized = " ".join(design.split())
    first_slice = design.split("### Risk-bearing vertical slice", 1)[1].split("\n### ", 1)[0]

    assert "## Integrity failure classification and alerting" in design
    assert "`ledger_integrity_failed`" in design
    assert "non-retryable" in normalized
    assert "never silently activates operator relay" in normalized
    assert "every subsequent response" in normalized
    assert "user-visible warning" in normalized
    assert "each participating agent warns on its next ledger interaction" in normalized
    assert "Integrity state and alerting" in first_slice
    for cause in (
        "duplicate sequence",
        "global sequence gap",
        "chain break",
        "counter/head disagreement",
        "rollback or divergence",
        "ledger-instance mismatch",
    ):
        assert cause in normalized


def test_a2a_ledger_chain_break_recovery_and_rollback_residual_are_explicit() -> None:
    design = _read(A2A_LEDGER_DESIGN)
    normalized = " ".join(design.split())
    accepted_residuals = design.split("### Accepted residuals", 1)[1].split("\n## ", 1)[0]
    first_slice = design.split("### Risk-bearing vertical slice", 1)[1].split("\n### ", 1)[0]
    operations = design.split("### Operations and extraction", 1)[1].split("\n## ", 1)[0]
    normalized_lower = normalized.lower()
    accepted_residuals_lower = " ".join(accepted_residuals.split()).lower()
    first_slice_lower = " ".join(first_slice.split()).lower()
    operations_lower = " ".join(operations.split()).lower()

    assert "## Chain-break recovery" in design
    assert "last independently verified sequence and digest" in normalized_lower
    assert "untrusted tail entries are never called final, repaired, or copied" in normalized_lower
    assert "quarantined read-only" in normalized_lower
    assert "successful full verification" in normalized_lower
    assert "linked replacement instance" in first_slice_lower
    assert "rollback occurs before any external client witness" in accepted_residuals_lower
    assert "backup manifest" in accepted_residuals_lower
    assert "head sequence and digest" in accepted_residuals_lower
    assert "periodic and at-rest integrity audits" in operations_lower
    assert "compare the backup manifest during restore" in operations_lower


def test_every_optimus_pool_entry_has_one_canonical_status() -> None:
    entries = _entry_sections(_read(OPTIMUS_POOL))

    assert len(entries) >= 41
    assert all(_status_token(body) for body in entries.values())


def test_p996_aggregate_uses_canonical_closed_status() -> None:
    pool_text = _read(OPTIMUS_POOL)
    section = pool_text.split("## P9.96 Task 9 Disclosed Follow-Ups", 1)[1].split(
        "\n## Closed Historical Follow-Ups", 1
    )[0]

    assert _status_token(section) == "Closed"


def test_fu_index_is_an_exact_projection_of_stable_id_entries() -> None:
    pool_text = _read(OPTIMUS_POOL)
    entries = _entry_sections(pool_text)
    expected: dict[str, tuple[str, str]] = {}
    for heading, body in entries.items():
        match = FU_HEADING_RE.fullmatch(heading)
        if match is None:
            continue
        identity = match.group("identity")
        assert identity not in expected
        expected[identity] = (match.group("title"), _status_token(body))

    assert _fu_index_rows(pool_text) == expected


def test_every_relative_optimus_pool_link_resolves() -> None:
    targets = _relative_link_targets(_read(OPTIMUS_POOL))

    assert targets
    for target in targets:
        assert (OPTIMUS_POOL.parent / target).resolve().exists(), target


def test_promoted_targets_resolve_inside_plan_directory() -> None:
    entries = _entry_sections(_read(OPTIMUS_POOL))
    promoted = tuple(
        token
        for token in (_status_token(body) for body in entries.values())
        if token.startswith("Promoted -> ")
    )

    assert promoted
    for token in promoted:
        match = PROMOTED_STATUS_RE.match(f"{token}.")
        assert match is not None
        target = urlsplit(match.group("target"))
        assert not target.scheme and target.path
        resolved = (OPTIMUS_POOL.parent / target.path).resolve()
        assert resolved.is_relative_to(PLANS_ROOT.resolve())
        assert resolved.is_file()


def test_settled_entries_do_not_label_historical_defects_as_current() -> None:
    forbidden = (
        "**Origin / current behavior:**",
        "**Also found:** No launcher exists",
        "The committed `uv.lock` is out of sync",
        "`tools/verify_plan996_logging_surfaces.py` raises",
    )
    for body in _entry_sections(_read(OPTIMUS_POOL)).values():
        token = _status_token(body)
        if token not in {"Closed", "Partially implemented", "Reviewed disposition"}:
            continue
        assert all(phrase not in body for phrase in forbidden)


def test_gateway_mcp_row_records_the_real_plan_118_boundary() -> None:
    pool_text = _read(OPTIMUS_POOL)
    row = _feature_row(pool_text, "P11-FEAT-GATEWAY-MCP")
    plan = _read(
        REPO_ROOT / "docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md"
    )
    checked = len(re.findall(r"^- \[x\]", plan, re.MULTILINE))
    unchecked = len(re.findall(r"^- \[ \]", plan, re.MULTILINE))

    assert "2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md" in row
    assert "2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md" in row
    assert checked and unchecked
    assert f"{checked} of {checked + unchecked}" in row
    assert "PR #116" in row and "PR #118" in row
    assert "next unused" not in pool_text.lower()


def test_plan_118_status_matches_its_checked_task_boundary() -> None:
    plan = _read(REPO_ROOT / "docs/superpowers/plans/2026-08-06-plan-11-8-p11-feat-gateway-mcp-implementation.md")
    normalized = re.sub(r"\s+", " ", plan)
    checked = len(re.findall(r"^- \[x\]", plan, re.MULTILINE))
    unchecked = len(re.findall(r"^- \[ \]", plan, re.MULTILINE))

    assert "**Status:** Partially implemented." in plan
    assert "Tasks 0-7 are complete" in normalized
    assert "Task 8 Step 1 is complete" in normalized
    assert "Task 8 Steps 2-4 and Task 9 are incomplete" in normalized
    assert checked and unchecked
    assert f"{checked} of {checked + unchecked}" in normalized


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
