"""Repository invariants for the Optimus and evidence/handoff open-work pools."""

from __future__ import annotations

import hashlib
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
OPTIMUS_POOL = REPO_ROOT / "docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"
PRODUCT_POOL = REPO_ROOT / "docs/superpowers/plans/evidence-handoff-open-work-pool.md"
A2A_LEDGER_DESIGN = REPO_ROOT / "docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md"
A2A_LEDGER_IMPLEMENTATION_PLAN = REPO_ROOT / "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md"
PLANS_ROOT = REPO_ROOT / "docs/superpowers/plans"
PLAN_985 = REPO_ROOT / "docs/superpowers/plans/2026-07-11-plan-9-85-multi-turn-read-observe-replan.md"
PLAN_987 = REPO_ROOT / "docs/superpowers/plans/2026-07-12-plan-9-87-model-initiated-replanning-live-refusal.md"
PLAN_999 = REPO_ROOT / "docs/superpowers/plans/2026-07-22-plan-9-99-credential-uri-security-snapshot-canonicalization.md"
PLAN_114 = REPO_ROOT / "docs/superpowers/plans/2026-07-28-plan-11-4-gateway-core-migration.md"
PLAN_119 = REPO_ROOT / "docs/superpowers/plans/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-implementation.md"
PHASE_1_ROADMAP = REPO_ROOT / "docs/superpowers/plans/2026-07-01-phase-1-roadmap.md"
PLAN_11_CHARTER = REPO_ROOT / "docs/superpowers/plans/2026-07-25-plan-11-v1-milestone-charter.md"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"
OPTIMUS_POOL_LINK_TARGET = "2026-07-23-consolidated-deferred-followups-backlog.md"

HISTORICAL_PLAN_117_AMENDMENTS = (
    "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md",
    "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md",
    "docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md",
)

HISTORICAL_NUMBERING_PROVENANCE = {
    "docs/superpowers/plans/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md": (
        "FA35912C3E5AC343A1092E7B5A88CA93C0E1293061CB53D5810BB1BA3C1002F8",
        "in-scope",
        "editable",
        "not digest-pinned",
        "deliberately unchanged",
    ),
    "docs/superpowers/specs/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-design.md": (
        "5608AD5520B8960E070A4A4F32C992D152A2CA19F21C177B44AC9805F371F3AA",
        "pinned elsewhere",
        "outside the covered set",
        "never edit",
    ),
    "docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md": (
        "AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8",
        "one of the 13 immutable",
        "never edit",
    ),
    "docs/superpowers/specs/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-design.md": (
        "BBB033051B8238A50E72D20F6C59A79BF94A0EBE19A43428CCB440EAF8B37F73",
        "not digest-pinned",
        "outside the covered set",
        "deliberately unchanged",
    ),
}

FROZEN_AUTHORITY_MARKER = "Frozen approval bytes — live status is owned by the consolidated open-work pool."
PROTECTED_BLOB_SHA256 = {
    "docs/superpowers/plans/2026-07-23-plan-10-2-p9-96-fu7-effective-row-display-provenance.md": (
        "4303D6AD5C44ED62A85A0509C8C87366505D4D470DD7BC4E0B4309BBE6E3C771"
    ),
    "docs/superpowers/plans/2026-07-24-plan-10-3-uv-lock-surface-audit-remediation.md": (
        "E66ECA48C588E7DB618D4850FDF0CEE901B4966BC0AB405E21C857AE6BE24F32"
    ),
    "docs/superpowers/plans/2026-07-25-plan-11-1-p11-feat-gateway-core-implementation.md": (
        "254A6ACC56511BBCCEB8FC101B190F213FD65450327145C88979077D845D6D3E"
    ),
    "docs/superpowers/plans/2026-07-26-plan-11-2-p11-feat-gateway-tools-implementation.md": (
        "8C96C9BFA67FB87F4A90FAE37169D27B437C5FD0CEE3AB2E6AB399E67B2874E5"
    ),
    "docs/superpowers/plans/2026-07-28-plan-11-5-p11-feat-gateway-cost-obs-implementation.md": (
        "0BAC146974984EA663B7A59802A1B5ED74F90EB682F855C0E05AAAB5B9A2C396"
    ),
    "docs/superpowers/plans/2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md": (
        "F52AD9A5A85DC50B0DFD3206B6BD09FD8FF0AE79B1A6049DF1017F978B1C462D"
    ),
    "docs/superpowers/plans/2026-08-02-plan-11-7-zed-server-side-custody-feasibility-amendment.md": (
        "79F3C92A852CB7EAA6108D8F0757F6612A0C908FE032CE7CFAB58B46721C06E6"
    ),
    "docs/superpowers/plans/2026-08-02-plan-11-7-origin-a-fixture-v2-amendment.md": (
        "5BB327D88761AE329869B90866839D03F61EFF6AF0E5AE47F8D3D7551F849A4D"
    ),
    "docs/superpowers/plans/2026-08-04-plan-11-7-retry-preflight-gate-amendment.md": (
        "106FD92B8E43F44A7115D7EDB1F9CF1E3EE643E4B6F594FA656FB4119A969B82"
    ),
    "docs/superpowers/specs/2026-07-15-plan-9-96-operator-controlled-debug-and-launch-trust-security-design.md": (
        "8B67FC187B92F0B66A9932AAAD9A013C476C19C165A1044F57F338245A01786C"
    ),
    "docs/superpowers/specs/2026-07-26-plan-11-2-p11-feat-gateway-tools-design.md": (
        "2E679F105A250C7DF9F3757F72C43810B92810DD080EC6A4A985B778D163BFEC"
    ),
    "docs/superpowers/specs/2026-08-04-plan-11-7-retry-preflight-gate-design.md": (
        "EB34FA10148CE813A03E60E0770116ABA4AC9857E4DFBEE87E00C39BFDB0D392"
    ),
    "docs/superpowers/specs/2026-08-06-plan-11-8-p11-feat-gateway-mcp-design.md": (
        "AC48C0AEF1778D6EBE93005BC3993AE204F81A1C59CDC8DB17CFB7EDB6A040F8"
    ),
    "docs/superpowers/specs/2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md": (
        "B445693AFB9B110E61D860F1B63D8836FF0EA651E0AC327BABA1CC906C84543B"
    ),
}

EXPECTED_DOCUMENT_STATUSES = {
    PLAN_985: (
        "Partially implemented. 72 of 78 plan checkboxes are complete; six historical "
        "execution/evidence checkboxes remain visibly unchecked. Nested follow-ups own their own status."
    ),
    PLAN_987: (
        "Closed through [Plan 9.88 Task 8 Outcome B]"
        "(2026-07-13-plan-9-88-fu4b-evidence-remediation-and-plan-9-87-closure.md"
        "#task-8-run-the-point-in-time-closure-ceremony-and-amend-plan-987-honestly). FU-4B "
        "remains accepted-open (exhausted, not qualifying). One unchecked commit step and the "
        "entire ten-item Definition of Done were never ticked and remain preserved as historical "
        "record; this status does not claim those checkboxes passed."
    ),
    PLAN_999: (
        "Partially implemented. Tasks 1-6 landed; three final verification and handoff checkboxes "
        "remain visibly unchecked."
    ),
    PLAN_114: "Closed. Implemented and merged to `main` through PR #91 (`d80e112`).",
    PLAN_119: "Closed. Implemented through PR #123 and PR #124.",
}

EXPECTED_NESTED_STATUSES = {
    PLAN_985: {
        "P9.85-FU-6: Planning gateway calls through `RetryController`": (
            "`PlanningLoopRunner` wraps each settled-turn Gateway call in `RetryController` with "
            "per-attempt usage callbacks. Runner-level accounting records stable "
            "`run_id:planning:{turn}:{wire_attempt}` request IDs when normalized usage fields are present."
        ),
    },
    PLAN_987: {
        "P9.87-FU-1: Mechanical current-raw-evidence grounding guard": (
            "Remains open. Plan 9.88 did not resolve this follow-up."
        ),
        "P9.85-FU-6: Billable failed retry aggregation and unknown transport cost": (
            "Remains open. Plan 9.87 expands retry-wrapper coverage but does not close unresolved "
            "accounting cases. Plan 9.88 did not resolve this follow-up."
        ),
        "Plan 11: Intelligent context selection and compression": "Unchanged and out of scope.",
    },
}

PLAN_11_SUMMARY_EVIDENCE = {
    "Plan 11.1": ("Closed", "PR #85"),
    "Plan 11.2": ("Closed", "PR #88"),
    "Plan 11.3": ("Closed", "PR #88"),
    "Plan 11.4": ("Closed", "PR #91"),
    "Plan 11.5": ("Closed", "PR #95"),
    "Plan 11.6": ("Merged", "PR #97"),
    "Plan 11.7": ("Partially implemented", "blocked"),
    "Plan 11.8": ("Historical", "Plan 11.12"),
    "Plan 11.9": ("Closed", "PR #123", "PR #124"),
}

EXPECTED_SETTLED_STATUSES = {
    "Plan 11.7 accepted risk: `optimus-redis` ACP-session durability boundary": "Reviewed disposition",
    "Plan 10.3 frozen-plan status correction (historical)": "Closed",
    "`uv.lock` missing direct dependencies: `keyring`, `redis`, and their transitive chain "
    "(disclosed 2026-07-23 during Plan 10.1 Task 1)": "Closed",
    "Tools: `SurfaceAuditError` frozen-dataclass CI wart "
    "(disclosed 2026-07-23 during Plan 10.1 Task 7)": "Closed",
}
EXPECTED_POOL_TABLE_IDENTITIES = (
    ("Feature slices", 0),
    ("Follow-up status index", 0),
    ("Settled risks and historical entries", 0),
    ("P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)", 0),
    ("P9.96 Task 9 Disclosed Follow-Ups (Closed; historical Plan 10 custody)", 1),
)
EXPECTED_NON_MEDIUM_PRIORITIES = {
    "P11-FU-1": "HIGH",
    "P11-FU-8": "LOW",
    "P11-FU-11": "HIGH",
    "P11.7-FU-1": "HIGH",
    "P11.5-FU-2": "HIGH",
}
EXPECTED_FEATURE_STATUS = {
    "P11-FEAT-GATEWAY-CORE": "Closed",
    "P11-FEAT-GATEWAY-TOOLS": "Closed",
    "P11-FEAT-GATEWAY-COST-OBS": "Closed",
    "P11-FEAT-GATEWAY-MCP": "Retired",
    "P11-FEAT-ZED-RESUME": "Partially implemented",
    "P11-FEAT-REGISTRY": "Open",
    "P11-FEAT-IDE": "Open",
    "Plan 12": "Open",
}
EXPECTED_FEATURE_SCOPE_TOKENS = {
    "P11-FEAT-GATEWAY-CORE": ("Plan 11.1", "PR #85", "Plan 11.4", "PR #91"),
    "P11-FEAT-GATEWAY-TOOLS": ("Plan 11.2", "PR #88"),
    "P11-FEAT-GATEWAY-COST-OBS": ("Plan 11.5", "PR #95", "P11.5-FU-1", "P11.5-FU-2"),
    "P11-FEAT-GATEWAY-MCP": ("Retired", "Plan 11.12", "Plan 11.8", "Plan 11.11", "Plan 11.13"),
    "P11-FEAT-ZED-RESUME": ("Partially implemented; blocked", "PR #108", "P11-FU-11", "Path A"),
    "P11-FEAT-REGISTRY": ("Ratified, unscheduled", "package and ACP versions are both `0.1.0`"),
    "P11-FEAT-IDE": ("Conditional",),
    "Plan 12": ("Post-v1.0",),
}
PROMOTED_PLAN_117_STATUS = (
    "Promoted -> [Plan 11.7](2026-07-29-plan-11-7-p11-feat-zed-resume-implementation.md)"
)
ALLOWED_PRIORITIES = frozenset({"HIGH", "MEDIUM", "LOW"})

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
        "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION",
        "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY",
        "EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH",
        "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY",
        "EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING",
        "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD",
    }
)
PRODUCT_OWNED_DOCS = frozenset(
    {
        "docs/superpowers/specs/evidence-handoff-a2a-ledger-design.md",
        "docs/superpowers/specs/evidence-handoff-evidence-collector-design.md",
        "docs/superpowers/specs/evidence-handoff-redaction-gate-design.md",
        "docs/superpowers/specs/evidence-handoff-zed-render-observation-design.md",
        "docs/superpowers/specs/evidence-handoff-a2a-ledger-remediation-scoping.md",
        "docs/superpowers/plans/evidence-handoff-evidence-collector-implementation.md",
        "docs/superpowers/plans/evidence-handoff-redaction-gate-implementation.md",
        "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation.md",
        "docs/superpowers/plans/evidence-handoff-risk-bearing-slice-implementation_v2.md",
        "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure.md",
        "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v2.md",
        "docs/superpowers/plans/evidence-handoff-a2a-not-shipped-closure_v3.md",
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
MARKDOWN_HEADING_RE = re.compile(r"^(?P<marks>#{1,6}) (?P<title>.+)$")
MARKDOWN_FENCE_RE = re.compile(r"^\s*(?P<marker>`{3,}|~{3,})")
MARKDOWN_TABLE_DELIMITER_CELL_RE = re.compile(r"^:?-{3,}:?$")
FROZEN_AUTHORITY_ROW_RE = re.compile(
    r"^- `(?P<path>docs/superpowers/(?:plans|specs)/[^`]+\.md)` — SHA-256 "
    r"`(?P<digest>[A-F0-9]{64})` — "
    + re.escape(FROZEN_AUTHORITY_MARKER)
    + r" Live owner: (?P<owner>.+)$",
    re.MULTILINE,
)
FIXED_STATUS_RE = re.compile(
    r"^(?P<token>Open|Partially implemented|Closed|Reviewed disposition)[.:](?:\s|$)"
)
PROMOTED_STATUS_RE = re.compile(
    r"^(?P<token>Promoted -> \[[^\]]+\]\((?P<target>[^)]+)\))[.:](?:\s|$)"
)
FU_INDEX_ROW_RE = re.compile(
    rf"^\|\s*`(?P<identity>{FU_ID_BODY})`\s*\|\s*(?P<item>[^|]+?)\s*\|"
    r"\s*(?P<status>.*?)\s*\|\s*(?P<priority>HIGH|MEDIUM|LOW)\s*\|"
    r"\s*(?P<owner>.*?)\s*\|\s*(?P<evidence>.*?)\s*\|\s*$",
    re.MULTILINE,
)
SETTLED_INDEX_ROW_RE = re.compile(
    r"^\|\s*(?P<item>[^|]+?)\s*\|\s*(?P<status>[^|]+?)\s*\|"
    r"\s*(?P<priority>HIGH|MEDIUM|LOW)\s*\|\s*(?P<evidence>.*?)\s*\|\s*$",
    re.MULTILINE,
)
PLAN_11_SNAPSHOT_ROW_RE = re.compile(
    r"^\|\s*(?P<plan>Plan 11\.[1-9])\s*\|\s*(?P<state>[^|]+?)\s*\|"
    r"\s*(?P<evidence>[^|]+?)\s*\|\s*$",
    re.MULTILINE,
)


def _read(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    if path.suffix == ".md":
        content = content.replace("~~", "")
    return content


def _head_blob_sha256(relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative_path}"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(result.stdout).hexdigest().upper()


def _status_lines_by_owner(text: str) -> tuple[tuple[tuple[str, ...], str], ...]:
    status_lines: list[tuple[tuple[str, ...], str]] = []
    heading_stack: list[str] = []
    fence_marker: str | None = None

    for line in text.splitlines():
        fence = MARKDOWN_FENCE_RE.match(line)
        if fence_marker is not None:
            if (
                fence is not None
                and fence.group("marker")[0] == fence_marker[0]
                and len(fence.group("marker")) >= len(fence_marker)
            ):
                fence_marker = None
            continue
        if fence is not None:
            fence_marker = fence.group("marker")
            continue

        heading = MARKDOWN_HEADING_RE.match(line)
        if heading is not None:
            level = len(heading.group("marks"))
            heading_stack[level - 1 :] = [heading.group("title")]
            continue

        status = STATUS_LINE_RE.fullmatch(line)
        if status is not None:
            status_lines.append((tuple(heading_stack), status.group("value").strip()))

    assert fence_marker is None
    return tuple(status_lines)


def _document_status(text: str) -> str:
    status_lines = _status_lines_by_owner(text)
    matches = tuple(value for owner, value in status_lines if len(owner) == 1)
    if not matches:
        charter_owner = ("Plan 11 v1.0 Milestone Charter", "Status and baseline")
        matches = tuple(value for owner, value in status_lines if owner == charter_owner)
    assert len(matches) == 1
    return matches[0]


def _nested_statuses(path: Path) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for owner, value in _status_lines_by_owner(_read(path)):
        if len(owner) == 1:
            continue
        heading = owner[-1]
        assert heading not in statuses
        statuses[heading] = value
    return statuses


def _frozen_authority_rows(text: str) -> tuple[tuple[str, str, str], ...]:
    heading = "## Frozen approval bytes and live-status authority"
    assert heading in text
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    return tuple(
        (match.group("path"), match.group("digest"), match.group("owner").strip())
        for match in FROZEN_AUTHORITY_ROW_RE.finditer(section)
    )


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


def _resolution(status: str) -> str:
    if status in {"Closed", "Reviewed disposition"}:
        return "resolved"
    if status in {"Open", "Partially implemented"} or status.startswith("Promoted -> "):
        return "unresolved"
    raise AssertionError(status)


def _fu_index_rows(text: str) -> dict[str, tuple[str, str]]:
    section = text.split("## Follow-up status index", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, tuple[str, str]] = {}
    for match in FU_INDEX_ROW_RE.finditer(section):
        identity = match.group("identity")
        assert identity not in rows
        rows[identity] = (match.group("item").strip(), match.group("status").strip())
    return rows


def _settled_index_rows(text: str) -> dict[str, str]:
    heading = "## Settled risks and historical entries"
    assert heading in text
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows: dict[str, str] = {}
    for match in SETTLED_INDEX_ROW_RE.finditer(section):
        item = match.group("item").strip()
        assert item not in rows
        rows[item] = match.group("status").strip()
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
    pattern = re.compile(rf"^\|\s*`{re.escape(identity)}`\s*\|")
    return next(line for line in text.splitlines() if pattern.match(line))


def _markdown_table_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    assert stripped.startswith("|") and stripped.endswith("|")
    return tuple(cell.strip() for cell in stripped[1:-1].split("|"))


def _markdown_tables(
    text: str,
) -> tuple[tuple[tuple[str, int], tuple[str, ...], tuple[dict[str, str], ...]], ...]:
    lines = text.splitlines()
    tables: list[tuple[tuple[str, int], tuple[str, ...], tuple[dict[str, str], ...]]] = []
    identities: set[tuple[str, int]] = set()
    ordinals: Counter[str] = Counter()
    nearest_h2: str | None = None
    fence_marker: str | None = None
    index = 0

    while index < len(lines):
        line = lines[index]
        fence = MARKDOWN_FENCE_RE.match(line)
        if fence_marker is not None:
            if (
                fence is not None
                and fence.group("marker")[0] == fence_marker[0]
                and len(fence.group("marker")) >= len(fence_marker)
            ):
                fence_marker = None
            index += 1
            continue
        if fence is not None:
            fence_marker = fence.group("marker")
            index += 1
            continue

        heading = MARKDOWN_HEADING_RE.match(line)
        if heading is not None and len(heading.group("marks")) == 2:
            nearest_h2 = heading.group("title")
            index += 1
            continue

        if index + 1 >= len(lines) or not line.strip().startswith("|"):
            index += 1
            continue
        header = _markdown_table_cells(line)
        delimiter = _markdown_table_cells(lines[index + 1])
        if len(delimiter) != len(header) or not all(
            MARKDOWN_TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in delimiter
        ):
            index += 1
            continue

        assert nearest_h2 is not None
        identity = (nearest_h2, ordinals[nearest_h2])
        ordinals[nearest_h2] += 1
        assert identity not in identities
        identities.add(identity)

        rows: list[dict[str, str]] = []
        index += 2
        while index < len(lines) and lines[index].strip().startswith("|"):
            cells = _markdown_table_cells(lines[index])
            assert len(cells) == len(header)
            rows.append(dict(zip(header, cells, strict=True)))
            index += 1
        tables.append((identity, header, tuple(rows)))

    assert fence_marker is None
    assert len(tables) == 5
    return tuple(tables)


def _h2_section(text: str, title_prefix: str) -> str:
    headings = tuple(SECTION_HEADING_RE.finditer(text))
    matches = tuple(
        (index, heading)
        for index, heading in enumerate(headings)
        if heading.group("level") == "##" and heading.group("title").startswith(title_prefix)
    )
    assert len(matches) == 1
    index, heading = matches[0]
    end = next(
        (
            candidate.start()
            for candidate in headings[index + 1 :]
            if candidate.group("level") == "##"
        ),
        len(text),
    )
    return text[heading.end() : end]


def _has_semantic_anchor_group(text: str, *anchors: str) -> bool:
    blocks = re.split(r"\n(?=- )|\n\s*\n", text)
    normalized_anchors = tuple(" ".join(anchor.casefold().split()) for anchor in anchors)
    return any(
        all(anchor in " ".join(block.casefold().split()) for anchor in normalized_anchors)
        for block in blocks
    )


def _contains_anchors_in_order(text: str, *anchors: str) -> bool:
    positions = tuple(text.find(anchor) for anchor in anchors)
    return all(position >= 0 for position in positions) and positions == tuple(sorted(positions))


def _plan_11_snapshot_rows(text: str) -> dict[str, tuple[str, str]]:
    section = _h2_section(text, "Plan 11 (")
    rows: dict[str, tuple[str, str]] = {}
    for match in PLAN_11_SNAPSHOT_ROW_RE.finditer(section):
        plan = match.group("plan")
        assert plan not in rows
        rows[plan] = (match.group("state").strip(), match.group("evidence").strip())
    return rows


def test_immutable_documents_match_approved_head_blobs() -> None:
    actual = {path: _head_blob_sha256(path) for path in PROTECTED_BLOB_SHA256}

    assert actual == PROTECTED_BLOB_SHA256


def test_immutable_pool_authority_rows_are_an_exact_projection() -> None:
    rows = _frozen_authority_rows(_read(OPTIMUS_POOL))
    paths = Counter(path for path, _digest, _owner in rows)
    projected = {path: digest for path, digest, _owner in rows}

    assert len(rows) == len(PROTECTED_BLOB_SHA256)
    assert paths == Counter(PROTECTED_BLOB_SHA256.keys())
    assert projected == PROTECTED_BLOB_SHA256
    assert all(owner for _path, _digest, owner in rows)


def test_historical_numbering_provenance_has_durable_pin_custody() -> None:
    pool = _read(OPTIMUS_POOL)
    heading = "#### Historical numbering-rule provenance"

    assert heading in pool
    section = pool.split(heading, 1)[1].split("\n## ", 1)[0]
    for path, anchors in HISTORICAL_NUMBERING_PROVENANCE.items():
        assert _has_semantic_anchor_group(section, path, *anchors)


def test_publication_plan_custody_is_a_real_indexed_pool_entry() -> None:
    pool = _read(OPTIMUS_POOL)
    heading = "P11-FU-27: Publication-Plan Historical-State Reconciliation"
    entries = _entry_sections(pool)

    assert heading in entries
    body = entries[heading]
    assert _status_token(body) == "Open"
    assert _fu_index_rows(pool)["P11-FU-27"] == (
        "Publication-Plan Historical-State Reconciliation",
        "Open",
    )
    for anchor in (
        "2026-08-05-mcp-gateway-architecture-amendment-publication-plan.md",
        "Task 10 Steps 1-7",
        "Task 11 Step 7",
        "verification.md",
        "PR #113",
    ):
        assert anchor in body

    tables = {
        identity: rows for identity, _header, rows in _markdown_tables(pool)
    }
    followup_rows = tables[("Follow-up status index", 0)]
    row = next(row for row in followup_rows if row["ID"] == "`P11-FU-27`")
    assert row["Priority"] == "MEDIUM"


def test_nested_status_parser_ignores_fenced_plan_985_example() -> None:
    statuses = _status_lines_by_owner(_read(PLAN_985))
    values = tuple(value for _owner, value in statuses)

    assert all("Tracked, not yet scheduled" not in value for value in values)
    assert _nested_statuses(PLAN_985) == EXPECTED_NESTED_STATUSES[PLAN_985]


def test_nested_statuses_in_plan_987_remain_exact() -> None:
    assert _nested_statuses(PLAN_987) == EXPECTED_NESTED_STATUSES[PLAN_987]


def test_document_status_accepts_charter_status_and_only_that_depth_two_owner() -> None:
    charter = (
        "# Plan 11 v1.0 Milestone Charter\n\n"
        "## Status and baseline\n\n"
        "**Status:** Ratified sentinel.\n"
    )
    non_charter = "# Another document\n\n## Status and baseline\n\n**Status:** Nested sentinel.\n"

    assert _document_status(charter) == "Ratified sentinel."
    with pytest.raises(AssertionError):
        _document_status(non_charter)


def test_roadmap_plan_11_snapshot_is_complete_and_defers_item_state_to_pool() -> None:
    roadmap = _read(PHASE_1_ROADMAP)
    plan_11_section = _h2_section(roadmap, "Plan 11 (")
    rows = _plan_11_snapshot_rows(roadmap)

    assert rows.keys() == PLAN_11_SUMMARY_EVIDENCE.keys()
    for plan, expected_tokens in PLAN_11_SUMMARY_EVIDENCE.items():
        row = " | ".join(rows[plan])
        assert all(token in row for token in expected_tokens)
    assert OPTIMUS_POOL_LINK_TARGET in _relative_link_targets(plan_11_section)


def test_charter_is_ratified_and_maps_completed_plan_11_lanes() -> None:
    charter = _read(PLAN_11_CHARTER)
    revised_map = _h2_section(charter, "Revised sub-plan map")

    assert _document_status(charter).startswith("Ratified")
    assert OPTIMUS_POOL_LINK_TARGET in _relative_link_targets(charter)
    assert all(plan in revised_map for plan in PLAN_11_SUMMARY_EVIDENCE)
    assert "Plan 11.3" in _feature_row(charter, "P11-FEAT-GATEWAY-TOOLS")
    assert "Plan 11.9" in _feature_row(charter, "P11-FEAT-ZED-RESUME")
    assert "Charter amendment draft for review; no implementation sub-plan is authorized" not in charter


def test_plan_versioning_uses_forward_only_semantic_anchor_groups() -> None:
    agents = _h2_section(_read(AGENTS_FILE), "Plan Fidelity And Anti-Drift Guardrails")

    assert _has_semantic_anchor_group(agents, "XYZ.md", "XYZ_v2.md", "XYZ_v3.md")
    assert _has_semantic_anchor_group(agents, "_v1", "_v2", "immutable")
    assert _has_semantic_anchor_group(agents, "consolidated pool", "live version")
    assert _has_semantic_anchor_group(agents, "going forward", "dated amendment", "retroactively")
    assert _has_semantic_anchor_group(
        agents,
        "evidence-handoff-risk-bearing-slice-implementation.md",
        "evidence-handoff-risk-bearing-slice-implementation_v2.md",
    )
    for relative_path in HISTORICAL_PLAN_117_AMENDMENTS:
        assert (REPO_ROOT / relative_path).is_file()
        assert relative_path in PROTECTED_BLOB_SHA256


def test_linear_numbering_semantics_reject_interstitial_and_nested_shapes() -> None:
    agents = _h2_section(_read(AGENTS_FILE), "Plan Fidelity And Anti-Drift Guardrails")
    charter_text = _read(PLAN_11_CHARTER)
    charter = _h2_section(charter_text, "Plan 11 feature-ID and plan-number allocation")

    for text in (agents, charter):
        assert _contains_anchors_in_order(text, "11.9", "11.10", "11.11")
        assert _has_semantic_anchor_group(text, "9.975", "forbidden")
        assert _has_semantic_anchor_group(text, "N.M.1", "forbidden")
        assert _has_semantic_anchor_group(text, "revision", "same plan number", "_vN")
        assert _has_semantic_anchor_group(text, "independently schedulable", "next linear plan number")

    charter_lower = charter_text.casefold()
    assert "next unused single-decimal" not in charter_lower
    assert "next-unused-single-decimal" not in charter_lower
    assert "two-decimal numbers such as `11.11` are never valid" not in charter_lower


def test_markdown_tables_keep_sibling_tables_under_one_h2() -> None:
    markdown = """\
## Feature slices

| Identity | Status |
|---|---|
| FEATURE-A | Open |

## Follow-up status index

| ID | Status |
|---|---|
| FU-1 | Open |

## Settled risks and historical entries

| Item | Status |
|---|---|
| Historical item | Closed |

## P9.96 Task 9 Disclosed Follow-Ups

| ID | Summary |
|---|---|
| P9.96-FU-1 | Summary text |

| ID | Disposition |
|---|---|
| P9.96-FU-1 | Closed |
"""

    assert _markdown_tables(markdown) == (
        (("Feature slices", 0), ("Identity", "Status"), ({"Identity": "FEATURE-A", "Status": "Open"},)),
        (("Follow-up status index", 0), ("ID", "Status"), ({"ID": "FU-1", "Status": "Open"},)),
        (
            ("Settled risks and historical entries", 0),
            ("Item", "Status"),
            ({"Item": "Historical item", "Status": "Closed"},),
        ),
        (
            ("P9.96 Task 9 Disclosed Follow-Ups", 0),
            ("ID", "Summary"),
            ({"ID": "P9.96-FU-1", "Summary": "Summary text"},),
        ),
        (
            ("P9.96 Task 9 Disclosed Follow-Ups", 1),
            ("ID", "Disposition"),
            ({"ID": "P9.96-FU-1", "Disposition": "Closed"},),
        ),
    )


@pytest.mark.parametrize(("path", "expected"), tuple(EXPECTED_DOCUMENT_STATUSES.items()))
def test_w1_document_level_status_is_exact(path: Path, expected: str) -> None:
    assert _document_status(_read(path)) == expected


def test_plan_987_document_level_closure_preserves_historical_unchecked_boxes() -> None:
    plan = _read(PLAN_987)
    task_8 = plan.split("### Task 8:", 1)[1].split("\n## Definition of Done", 1)[0]
    definition_of_done = plan.split("## Definition of Done", 1)[1].split("\n## Deferred Follow-Ups", 1)[0]

    assert len(re.findall(r"^- \[ \]", task_8, re.MULTILINE)) == 1
    assert len(re.findall(r"^- \[ \]", definition_of_done, re.MULTILINE)) == 10
    assert "Plan 9.88 Task 8 Outcome B" in _document_status(plan)
    assert "accepted-open (exhausted, not qualifying)" in _document_status(plan)


def test_product_features_have_exactly_one_pool_owner() -> None:
    optimus_rows = _feature_rows(_read(OPTIMUS_POOL))
    product_rows = _feature_rows(_read(PRODUCT_POOL))

    assert not (optimus_rows.keys() & product_rows.keys())
    assert all(optimus_rows[feature_id] + product_rows[feature_id] == 1 for feature_id in PRODUCT_FEATURE_IDS)
    assert PRODUCT_FEATURE_IDS <= product_rows.keys()


A2A_NOT_SHIPPED_VERBATIM = (
    "The feature is not on the ordinary Optimus runtime path and lifecycle activation is opt-in by "
    "default. However, merged code and installed console entry points remain manually callable. "
    "They are unsupported and untrusted and must not be enabled or used for trusted workflows."
)
A2A_REMEDIATION_SLICE_IDS = (
    "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING",
    "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD",
)
A2A_BACKTICK_ONLY_REVIEW_DOCS = (
    "docs/superpowers/reviews/evidence-handoff-a2a-ledger-independent-audit.md",
    "docs/superpowers/reviews/evidence-handoff-a2a-ledger-sealed-reviewer-findings.md",
    "docs/superpowers/reviews/evidence-handoff-a2a-remediation-scoping-review.md",
    "docs/superpowers/reviews/evidence-handoff-a2a-not-shipped-closure-review.md",
)


def test_a2a_ledger_row_records_not_shipped_state() -> None:
    pool_text = _read(PRODUCT_POOL)
    row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER")
    row_lower = row.lower()

    assert "**Closed**" not in row
    assert "72c3b82" not in row
    assert "not shipped" in row_lower
    assert "not supported" in row_lower
    assert "not trusted" in row_lower
    assert "`e5f7e339`" in row
    assert "NOT SOUND" in row
    assert "17 findings, 3 Critical" in row
    assert "`658042d`" in row
    assert "25 inclusive commits from `8735885`" in row
    assert "PR #128" in row and "`7b5865f`" in row
    assert "PR #129" in row and "`74f7104`" in row
    assert "code remains merged" in row
    assert "console scripts remain installed" in row
    assert "default-off" in row
    assert "No ordinary Optimus" in row and "runtime import" in row
    assert A2A_NOT_SHIPPED_VERBATIM in row
    assert "[closure plan `_v3`](evidence-handoff-a2a-not-shipped-closure_v3.md)" in row
    assert (
        "[remediation-scoping contract](../specs/evidence-handoff-a2a-ledger-remediation-scoping.md)"
    ) in row
    for doc in A2A_BACKTICK_ONLY_REVIEW_DOCS:
        assert f"`{doc}`" in row
        assert f"]({doc})" not in row
    for slice_id in A2A_REMEDIATION_SLICE_IDS:
        assert f"`{slice_id}`" in row
    assert A2A_LEDGER_DESIGN.is_file()

    header_line = next(
        line
        for line in pool_text.splitlines()
        if line.strip() == "| Identity | State | Priority | Scope detail |"
    )
    assert header_line.count("Priority") == 1

    non_medium: dict[str, str] = {}
    for line in pool_text.splitlines():
        match = FEATURE_ROW_RE.match(line)
        if match is None:
            continue
        cells = _markdown_table_cells(line)
        assert len(cells) == 4
        identity = cells[0].strip("`")
        priority = cells[2]
        assert priority in ALLOWED_PRIORITIES
        if priority != "MEDIUM":
            non_medium[identity] = priority
    assert non_medium == {"EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE": "HIGH"}
    assert PRODUCT_FEATURE_IDS <= _feature_rows(pool_text).keys()

    assert re.search(r"\bPriority:", pool_text) is None
    assert "**HIGH** priority" not in pool_text


EXPECTED_OBLIGATIONS: dict[str, tuple[str, str]] = {
    "C1": ("CRITICAL", "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION"),
    "C2": ("CRITICAL", "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY"),
    "C3": ("CRITICAL", "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION"),
    "H4": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH"),
    "H5": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH"),
    "H6": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-DATAPATH"),
    "H7": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION"),
    "H8": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY"),
    "H9": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION"),
    "H10": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD"),
    "H11": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD"),
    "H12a": ("HIGH", "program gate contract (pre-work, unscheduled)"),
    "H12b": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD"),
    "H13": ("HIGH", "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY"),
    "M14": ("MEDIUM", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY"),
    "M15": ("MEDIUM", "EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION"),
    "M16a": ("MEDIUM", "EVIDENCE-HANDOFF-FEAT-LEDGER-AUDIT-WIRING"),
    "M16b": ("MEDIUM", "EVIDENCE-HANDOFF-FEAT-LEDGER-RUNTIME-BOUNDARY"),
    "M16c": ("MEDIUM", "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY"),
    "M17": ("MEDIUM", "this closure plan"),
}


def test_a2a_ledger_obligations_table_matches_expected() -> None:
    pool_text = _read(PRODUCT_POOL)
    section = _h2_section(pool_text, "A2A ledger audit obligations")
    table_lines = [line for line in section.splitlines() if line.strip().startswith("|")]

    header = _markdown_table_cells(table_lines[0])
    assert header == ("Obligation", "Severity", "Owning slice", "Status", "Priority")
    assert header.count("Priority") == 1

    body_rows = [_markdown_table_cells(line) for line in table_lines[2:]]
    assert len(body_rows) == 20

    actual_obligations: dict[str, tuple[str, str]] = {}
    statuses: dict[str, str] = {}
    for cells in body_rows:
        assert len(cells) == 5
        obligation = cells[0].strip("`")
        severity, owner, status, priority = cells[1], cells[2].strip("`"), cells[3], cells[4]
        assert obligation not in actual_obligations
        actual_obligations[obligation] = (severity, owner)
        statuses[obligation] = status
        assert priority == "MEDIUM"

    assert actual_obligations == EXPECTED_OBLIGATIONS
    assert set(statuses.values()) <= {"Open", "**Closed**"}
    assert {obligation for obligation, status in statuses.items() if status == "**Closed**"} == {"M17"}

    a2a_row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER")
    assert "**Closed**" not in a2a_row

    for slice_id in A2A_REMEDIATION_SLICE_IDS:
        slice_row = _feature_row(pool_text, slice_id)
        assert "Tracked, Not Yet Scheduled" in slice_row


def test_adjacent_custody_rows_reflect_restored_dual_ownership() -> None:
    pool_text = _read(PRODUCT_POOL)

    design_refresh_row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-A2A-LEDGER-DESIGN-REFRESH")
    assert "integrity guards belong at operation entry" not in design_refresh_row
    assert "Restate the local store ladder as Docker Desktop PostgreSQL" in design_refresh_row
    assert "wslc removed" in design_refresh_row
    assert (
        "read-path verification only covers the unread range behind confirmed cursors"
        in design_refresh_row
    )
    assert "Session protocol admission is Option A" in design_refresh_row
    assert "EVIDENCE-HANDOFF-FEAT-LEDGER-INTEGRITY-BOUNDARY" in design_refresh_row
    assert "remains on this agenda" not in design_refresh_row
    assert "Option B session protocol admission vs binding" not in design_refresh_row

    at_rest_row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-AT-REST-INTEGRITY")
    assert "operator-invoked" not in at_rest_row
    assert "scheduled `IntegrityMonitor.verify_full()`" in at_rest_row
    assert "in-flight Task 6" not in at_rest_row
    assert "completed and archived Task 6" in at_rest_row

    credential_row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-CREDENTIAL-LIFECYCLE")
    assert "OAuth (MCP's OAuth 2.1 authorization framework)" in credential_row
    assert "Cursor (probe) fails tool discovery" in credential_row
    assert "EVIDENCE-HANDOFF-FEAT-LEDGER-EVIDENCE-DOD" in credential_row

    peer_row = _feature_row(pool_text, "EVIDENCE-HANDOFF-FEAT-PEER-LIVENESS-SIGNAL")
    assert "Task 10 capstone" not in peer_row
    assert "Task 11 release gates" not in peer_row
    assert "in-flight" not in peer_row

    optimus_text = _read(OPTIMUS_POOL)
    assert "hardened-Redis fallback path" not in optimus_text
    assert "the consolidated local-startup configuration source of truth" in optimus_text


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
    pool_text = _read(OPTIMUS_POOL)
    entries = _entry_sections(pool_text)
    indexed_headings = {
        f"{identity}: {item}" for identity, (item, _status) in _fu_index_rows(pool_text).items()
    }
    settled_headings = set(_settled_index_rows(pool_text))

    assert indexed_headings.isdisjoint(settled_headings)
    assert indexed_headings | settled_headings == set(entries)
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


def test_settled_index_is_an_exact_status_projection() -> None:
    pool_text = _read(OPTIMUS_POOL)
    entries = _entry_sections(pool_text)
    settled = _settled_index_rows(pool_text)

    assert settled == EXPECTED_SETTLED_STATUSES
    assert {heading: _status_token(entries[heading]) for heading in settled} == settled


def test_pool_tables_have_collision_safe_identities_and_valid_priority_cells() -> None:
    tables = _markdown_tables(_read(OPTIMUS_POOL))

    assert tuple(identity for identity, _header, _rows in tables) == EXPECTED_POOL_TABLE_IDENTITIES
    for _identity, header, rows in tables:
        assert header.count("Priority") == 1
        assert rows
        assert all(row["Priority"] in ALLOWED_PRIORITIES for row in rows)


def test_priority_seed_preserves_only_the_four_approved_non_medium_values() -> None:
    tables = {
        identity: (header, rows)
        for identity, header, rows in _markdown_tables(_read(OPTIMUS_POOL))
    }
    followup_header, followup_rows = tables[("Follow-up status index", 0)]

    assert followup_header == (
        "ID",
        "Item",
        "Status",
        "Priority",
        "Owning slice / designated plan",
        "Evidence",
    )
    followup_priorities = {row["ID"].strip("`"): row["Priority"] for row in followup_rows}
    assert {
        identity: priority
        for identity, priority in followup_priorities.items()
        if priority != "MEDIUM"
    } == EXPECTED_NON_MEDIUM_PRIORITIES
    assert all(
        row["Priority"] in {"MEDIUM", "LOW"}
        for identity, (_header, rows) in tables.items()
        if identity != ("Follow-up status index", 0)
        for row in rows
    )


def test_priority_is_authored_only_in_table_cells() -> None:
    assert re.search(r"\bPriority:", _read(OPTIMUS_POOL)) is None


def test_feature_status_is_canonical_and_state_prose_lives_in_scope_detail() -> None:
    tables = {
        identity: (header, rows)
        for identity, header, rows in _markdown_tables(_read(OPTIMUS_POOL))
    }
    header, rows = tables[("Feature slices", 0)]

    assert header == ("Identity", "Status", "Priority", "Scope detail")
    assert {row["Identity"].strip("`"): row["Status"] for row in rows} == EXPECTED_FEATURE_STATUS
    scopes = {row["Identity"].strip("`"): row["Scope detail"] for row in rows}
    assert scopes.keys() == EXPECTED_FEATURE_SCOPE_TOKENS.keys()
    for identity, expected_tokens in EXPECTED_FEATURE_SCOPE_TOKENS.items():
        assert all(token in scopes[identity] for token in expected_tokens)


def test_promoted_statuses_remain_exact_and_every_entry_status_has_a_resolution() -> None:
    pool_text = _read(OPTIMUS_POOL)
    entries = _entry_sections(pool_text)
    indexed = _fu_index_rows(pool_text)
    settled = _settled_index_rows(pool_text)
    followup_intro = pool_text.split("## Follow-up status index", 1)[1].split("| ID |", 1)[0]
    detail_statuses = {heading: _status_token(body) for heading, body in entries.items()}
    projected_statuses = {
        **{f"{identity}: {item}": status for identity, (item, status) in indexed.items()},
        **settled,
    }

    assert indexed["P9.8-FU-5"][1] == PROMOTED_PLAN_117_STATUS
    assert indexed["P11-FU-1"][1] == PROMOTED_PLAN_117_STATUS
    assert _resolution(PROMOTED_PLAN_117_STATUS) == "unresolved"
    assert "`Open`, `Promoted -> ...`, and `Partially implemented` are unresolved" in followup_intro
    assert "`Closed` and `Reviewed disposition` are resolved" in followup_intro
    assert projected_statuses == detail_statuses
    assert all(
        _resolution(status) == "resolved"
        for status in detail_statuses.values()
        if status in {"Closed", "Reviewed disposition"}
    )
    assert all(
        _resolution(status) == "unresolved"
        for status in detail_statuses.values()
        if status not in {"Closed", "Reviewed disposition"}
    )


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


def test_gateway_mcp_retirement_custody_is_current() -> None:
    pool_text = _read(OPTIMUS_POOL)
    row = _feature_row(pool_text, "P11-FEAT-GATEWAY-MCP")
    indexed = _fu_index_rows(pool_text)
    entries = _entry_sections(pool_text)
    roadmap = _read(PHASE_1_ROADMAP)
    charter = _read(PLAN_11_CHARTER)
    wont_do_ids = (
        "P11-FU-12",
        "P11-FU-13",
        "P11-FU-14",
        "P11-FU-15",
        "P11-FU-22",
    )

    assert "Retired" in _markdown_table_cells(row)
    assert "Plan 11.12" in row
    assert "historical" in row.lower()
    assert "Plan 11.8" in row and "Plan 11.11" in row
    assert "Plan 11.13" in row
    assert "P11-FEAT-REGISTRY" in row

    for fu_id in wont_do_ids:
        item, status = indexed[fu_id]
        assert status == "Closed"
        body = entries[f"{fu_id}: {item}"]
        assert _status_token(body) == "Closed"
        assert "won't-do" in body.casefold()
        assert "Plan 11.12" in body

    fu26_item, fu26_status = indexed["P11-FU-26"]
    fu26 = entries[f"P11-FU-26: {fu26_item}"]
    assert fu26_status == "Closed"
    assert _status_token(fu26) == "Closed"
    assert "obsolete-by-retirement" in fu26.casefold()
    assert "P11-FU-6" in fu26
    assert "WinError 10053" in fu26

    fu6_item, fu6_status = indexed["P11-FU-6"]
    fu6 = entries[f"P11-FU-6: {fu6_item}"]
    assert fu6_status == "Open"
    assert _status_token(fu6) == "Open"
    assert "WinError 10053" in fu6
    assert "Plan 11.12" in fu6
    assert "no production retry" in fu6.casefold()

    assert "Plan 11.13" in roadmap
    assert "historical" in _h2_section(roadmap, "Plan 11 (").casefold()
    assert "Plan 11.13" in charter
    assert "P11-FEAT-REGISTRY" in charter


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


def test_plan_1116_deadline_seams_keep_separate_scheduled_custody() -> None:
    """P11-FU-7 and P11-FU-19 must be scheduled separately under Plan 11.16."""
    pool = _read(OPTIMUS_POOL)
    indexed = _fu_index_rows(pool)
    entries = _entry_sections(pool)
    tables = {identity: rows for identity, _header, rows in _markdown_tables(pool)}
    followup_rows = tables[("Follow-up status index", 0)]

    fu7_item, fu7_status = indexed["P11-FU-7"]
    fu19_item, fu19_status = indexed["P11-FU-19"]
    p11_fu_7 = entries[f"P11-FU-7: {fu7_item}"]
    p11_fu_19 = entries[f"P11-FU-19: {fu19_item}"]
    fu7_row = next(row for row in followup_rows if row["ID"] == "`P11-FU-7`")
    fu19_row = next(row for row in followup_rows if row["ID"] == "`P11-FU-19`")

    def _lane_state(status: str) -> str:
        if status.startswith("Promoted -> ") and "Plan 11.16" in status:
            return "scheduled"
        if status == "Closed":
            return "closed"
        raise AssertionError(status)

    assert _lane_state(fu7_status) in {"scheduled", "closed"}
    assert _lane_state(fu19_status) in {"scheduled", "closed"}
    assert "Plan 11.16" in p11_fu_7
    assert "Plan 11.16" in p11_fu_19
    assert "P11-FU-19" not in fu7_row["Evidence"]
    assert "P11-FU-7" not in fu19_row["Evidence"]
