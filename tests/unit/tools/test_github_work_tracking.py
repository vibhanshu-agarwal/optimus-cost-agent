"""Plan 11.29 work-tracking migration: inventory coverage, fail-closed parsing and drafting rules."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools import github_work_tracking as gwt
from tools import github_work_tracking_rules as rules

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "reports" / "github-work-tracking-migration.json"

POOL = """\
# Pool

## Live implementation plan registry

| Plan | State | Backlog owner | Next gate |
|---|---|---|---|
| [Plan 11.23 — client-MCP runtime composition](plan-11-23.md) | `Blocked` | `P11-FU-20` | Task 6 live gate. |
| [Plan 12.1 — Plan/Chat advisory answer](plan-12-1.md) | `Blocked` | `P12-FU-1` | Dependency gate. |

## Follow-up status index

| ID | Item | Status | Priority | Owner | Evidence |
|---|---|---|---|---|---|
| `P11-FU-20` | Attach catalog | Partially implemented | MEDIUM | Live blocked Plan 11.23 Task 6 | report |
| `P11-FU-40` | Real Zed containment | Open | MEDIUM | `P11.26-CAND-1-RESOURCE-LIFETIME` | entry |
| `P11.25-FU-1` | Carriage | Promoted -> [Plan 12.1](plan-12-1.md) | MEDIUM | Plan 12.1 | entry |
| `P12-FU-1` | Advisory answers | Promoted -> [Plan 12.1](plan-12-1.md) | MEDIUM | Plan 12.1 | entry |

## A2A ledger audit obligations

| Obligation | Severity | Owning slice | Status | Priority |
|---|---|---|---|---|
| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |
| M17 | MEDIUM | archived closure plan | Closed | MEDIUM |

## Plan 11.26 H4 verifier follow-ups from Seam 2 checkpoint A

**Status:** Open. Filing is commissioned; verifier implementation is not.

## Open items

### P11-FU-20: Attach catalog

**Status:** Partially implemented. Live Plan 11.23 supersedes the production residual.

### P11-FU-40: Real Zed containment

**Status:** Open.

### P11.25-FU-1: Carriage

**Status:** Promoted -> [Plan 12.1](plan-12-1.md).

### P12-FU-1: Advisory answers

**Status:** Promoted -> [Plan 12.1](plan-12-1.md).

## Accepted risks and warnings

### Plan 11.7 accepted risk: Redis durability

**Status:** Reviewed disposition. Accepted as-is by the operator; recorded warning, not open work.
"""

PROGRAM = """\
## Child-plan status board

| Track | Child plan | Status | Scope owned by that plan |
|---|---|---|---|
| `HARDENING-TRACK-RUFF-LINT` | `ruff.md` | `Not drafted` | `HARDENING-ITEM-RUFF-LINT-RATCHET` |
| `HARDENING-TRACK-CI-GUARDRAILS` | `ci.md` | `Active` | `HARDENING-ITEM-LOCKFILE-CI-ENFORCEMENT` |

## MAIN-5 residuals under existing 11.x owners

### P11-FU-31: MAIN-5 synthetic-fixture debt

**Status:** Open.

### P11-FU-33: MAIN-5 shutdown repeatability evidence

**Status:** Closed. Through PR #219.
"""


def _unit(text: str, needle: str, source: str = "pool") -> str:
    """The unit key of the first line containing ``needle``."""
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f"{source}:{number}"
    raise AssertionError(f"fixture has no line containing {needle!r}")


def _record(**fields: Any) -> dict[str, Any]:
    record: dict[str, Any] = {"title": "fixture title", "priority": "MEDIUM", "rationale": "source-derived", "aliases": [], "related": []}
    record.update(fields)
    return record


def _good() -> dict[str, Any]:
    u = lambda needle: _unit(POOL, needle)  # noqa: E731 - local fixture shorthand
    return {
        "schema": gwt.SCHEMA,
        "baseline": {"commit": "fixture", "sources": {"pool": {"path": "pool.md", "blob": gwt.git_blob_id(POOL.encode())}}},
        "sections": [
            {"source": "pool", "title": "Live implementation plan registry", "classification": "migrated", "rationale": "live plans"},
            {"source": "pool", "title": "Follow-up status index", "classification": "migrated", "rationale": "index projection"},
            {"source": "pool", "title": "A2A ledger audit obligations", "classification": "mixed", "rationale": "open and closed rows"},
            {
                "source": "pool",
                "title": "Plan 11.26 H4 verifier follow-ups from Seam 2 checkpoint A",
                "classification": "migrated",
                "rationale": "section-level open record",
            },
            {"source": "pool", "title": "Open items", "classification": "migrated", "rationale": "entries"},
            {"source": "pool", "title": "Accepted risks and warnings", "classification": "not-work", "rationale": "accepted limits"},
        ],
        "records": [
            _record(id="plan:11.23", kind="plan", status="Blocked", disposition="migrate", target_issue=222, units=[u("[Plan 11.23")]),
            _record(id="plan:12.1", kind="plan", status="Blocked", disposition="migrate", units=[u("[Plan 12.1")]),
            _record(
                id="P11-FU-20",
                kind="follow-up",
                status="Partially implemented",
                disposition="migrate",
                target_issue=223,
                parent="plan:11.23",
                units=[u("| `P11-FU-20` | Attach"), u("### P11-FU-20")],
            ),
            _record(id="P11-FU-40", kind="follow-up", status="Open", disposition="migrate", units=[u("| `P11-FU-40`"), u("### P11-FU-40")]),
            _record(
                id="P11.25-FU-1",
                kind="follow-up",
                status="Promoted -> [Plan 12.1](plan-12-1.md)",
                disposition="migrate",
                parent="plan:12.1",
                units=[u("| `P11.25-FU-1`"), u("### P11.25-FU-1")],
            ),
            _record(
                id="P12-FU-1",
                kind="follow-up",
                status="Promoted -> [Plan 12.1](plan-12-1.md)",
                disposition="migrate",
                parent="plan:12.1",
                units=[u("| `P12-FU-1` | Advisory"), u("### P12-FU-1")],
            ),
            _record(id="A2A-C1", kind="obligation", status="Open", disposition="migrate", units=[u("| C1 |")], product="evidence-a2a"),
            _record(id="A2A-M17", kind="obligation", status="Closed", disposition="history", units=[u("| M17 |")]),
            _record(
                id="H4",
                kind="follow-up",
                status="Open. Filing is commissioned; verifier implementation is not.",
                disposition="migrate",
                units=[u("## Plan 11.26 H4 verifier")],
            ),
            _record(
                id="RISK",
                kind="risk",
                status="Reviewed disposition. Accepted as-is by the operator; recorded warning, not open work.",
                disposition="not-work",
                units=[u("### Plan 11.7 accepted risk")],
                priority=None,
            ),
        ],
    }


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _validate(tmp_path: Path, data: dict[str, Any], text: str = POOL) -> gwt.CoverageReport:
    return gwt.validate_inventory(gwt.load_inventory(_write(tmp_path, data)), {"pool": text.encode("utf-8")})


def _records(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in data["records"]}


def _with_source(data: dict[str, Any], text: str) -> dict[str, Any]:
    data["baseline"]["sources"]["pool"]["blob"] = gwt.git_blob_id(text.encode("utf-8"))
    return data


def _problems(tmp_path: Path, data: dict[str, Any], text: str = POOL) -> list[str]:
    return list(_validate(tmp_path, _with_source(data, text), text).problems)


# ---- the good fixture is complete ----


def test_good_fixture_inventory_is_complete(tmp_path: Path) -> None:
    report = _validate(tmp_path, _good())
    assert report.problems == ()
    assert report.ok


# ---- the six rules the plan names ----


def test_inventory_covers_all_source_sections(tmp_path: Path) -> None:
    data = _good()
    data["sections"] = [s for s in data["sections"] if s["title"] != "A2A ledger audit obligations"]
    assert any("A2A ledger audit obligations" in p and "unclassified section" in p for p in _problems(tmp_path, data))

    data = _good()
    data["sections"].append({"source": "pool", "title": "Invented section", "classification": "history", "rationale": "x"})
    assert any("Invented section" in p for p in _problems(tmp_path, data))


def test_missing_obligation_fails(tmp_path: Path) -> None:
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "A2A-C1"]
    assert any("C1" in p and "unclaimed" in p and "unresolved" in p for p in _problems(tmp_path, data))

    # Open work cannot be hidden by classifying its whole section as history.
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "H4"]
    for section in data["sections"]:
        if section["title"].startswith("Plan 11.26 H4"):
            section["classification"] = "history"
    assert any("H4" in p and "unclaimed" in p for p in _problems(tmp_path, data))

    # A record claiming open work as history needs an explicit terminal disposition.
    data = _good()
    _records(data)["P11-FU-40"]["disposition"] = "history"
    assert any("P11-FU-40" in p and "terminal" in p for p in _problems(tmp_path, data))


def test_duplicate_status_conflict_requires_disposition(tmp_path: Path) -> None:
    conflicting = POOL.replace("| `P11-FU-40` | Real Zed containment | Open |", "| `P11-FU-40` | Real Zed containment | Closed |")
    data = _good()
    _records(data)["P11-FU-40"]["status"] = "Open."  # the entry's own status text
    assert any("P11-FU-40" in p and "conflicting source statuses" in p for p in _problems(tmp_path, data, conflicting))

    _records(data)["P11-FU-40"]["status_conflict_disposition"] = "Entry is authoritative; index row is stale (reviewed)."
    assert _problems(tmp_path, data, conflicting) == []


def test_plan_item_distinct_acceptance_preserved(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["plan:11.23"]["units"] += records["P11-FU-20"]["units"]
    data["records"] = [r for r in data["records"] if r["id"] != "P11-FU-20"]
    assert any("plan:11.23" in p and "plan and item" in p for p in _problems(tmp_path, data))


def test_many_source_aliases_require_duplicate_rationale(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["P11.25-FU-1"]["units"] += records["P12-FU-1"]["units"]
    data["records"] = [r for r in data["records"] if r["id"] != "P12-FU-1"]
    assert any("P11.25-FU-1" in p and "duplicate rationale" in p for p in _problems(tmp_path, data))

    records["P11.25-FU-1"]["duplicate_rationale"] = "Same carriage obligation filed twice (reviewed)."
    assert _problems(tmp_path, data) == []

    data = _good()
    _records(data)["P12-FU-1"].update(disposition="duplicate", duplicate_of="P11.25-FU-1")
    assert any("P12-FU-1" in p and "duplicate rationale" in p for p in _problems(tmp_path, data))


def test_accepted_risk_with_unfinished_mitigation_not_excluded(tmp_path: Path) -> None:
    data = _good()
    _records(data)["RISK"]["mitigation_outstanding"] = True
    assert any("RISK" in p and "mitigation" in p for p in _problems(tmp_path, data))


def test_reviewed_disposition_units_always_need_a_record(tmp_path: Path) -> None:
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "RISK"]
    assert any("reviewed disposition always needs its own record" in p for p in _problems(tmp_path, data))


# ---- record metadata follows the pinned source ----


@pytest.mark.parametrize("status", ["Closed", "nonsense", None])
def test_record_status_is_a_source_status_snapshot(tmp_path: Path, status: str | None) -> None:
    data = _good()
    _records(data)["P11-FU-40"]["status"] = status  # its index row and entry both say Open
    assert any("P11-FU-40" in p and "source status" in p for p in _problems(tmp_path, data))


def test_a_status_disposition_cannot_override_a_source_status(tmp_path: Path) -> None:
    data = _good()
    _records(data)["P11-FU-40"].update(status="Closed", status_disposition="reviewed: treat as closed")
    assert any("P11-FU-40" in p and "source status" in p for p in _problems(tmp_path, data))

    data = _good()
    _records(data)["P11-FU-40"]["status_disposition"] = "reviewed: no change"
    assert any("P11-FU-40" in p and "cannot be overridden" in p for p in _problems(tmp_path, data))


CUSTODY = POOL + "\n## Custody register\n\n| Item | Owner |\n|---|---|\n| `HARDENING-ITEM-FIXTURE` | track |\n"


def _custody(**fields: Any) -> dict[str, Any]:
    data = _good()
    data["sections"].append({"source": "pool", "title": "Custody register", "classification": "migrated", "rationale": "items"})
    record = _record(id="HARDENING-ITEM-FIXTURE", kind="item", status="Open", disposition="migrate", units=[_unit(CUSTODY, "ITEM-FIXTURE")])
    record.update(fields)
    data["records"].append(record)
    return data


def test_a_synthesized_status_needs_a_reviewed_disposition_and_a_known_token(tmp_path: Path) -> None:
    disposition = "the register has no status column by design; open until its track delivers (reviewed)"
    assert _problems(tmp_path, _custody(status_disposition=disposition), CUSTODY) == []

    assert any("status disposition" in p for p in _problems(tmp_path, _custody(), CUSTODY))
    assert any("not a known status" in p for p in _problems(tmp_path, _custody(status="nonsense", status_disposition=disposition), CUSTODY))
    assert any("migrates without a status" in p for p in _problems(tmp_path, _custody(status=None), CUSTODY))


@pytest.mark.parametrize(
    ("record_id", "priority", "expected"),
    [
        ("P11-FU-40", "nonsense", "is not one of"),  # its index row says MEDIUM
        ("P11-FU-40", "HIGH", "source priority"),
        ("P11-FU-40", None, "is not one of"),
        ("plan:11.23", "nonsense", "is not one of"),  # the registry has no priority column
        ("plan:11.23", "HIGH", "priority disposition"),
    ],
)
def test_record_priority_is_the_source_value_or_the_default(tmp_path: Path, record_id: str, priority: str | None, expected: str) -> None:
    data = _good()
    _records(data)[record_id]["priority"] = priority
    assert any(record_id in p and expected in p for p in _problems(tmp_path, data))


def test_a_priority_disposition_explains_a_non_default_value_without_a_source(tmp_path: Path) -> None:
    data = _good()
    _records(data)["plan:11.23"].update(priority="HIGH", priority_disposition="issue body states P0; mapped to the highest label")
    assert _problems(tmp_path, data) == []

    data = _good()
    _records(data)["P11-FU-40"].update(priority="HIGH", priority_disposition="reviewed: raise it")
    assert any("P11-FU-40" in p and "source priority" in p for p in _problems(tmp_path, data))

    data = _good()
    _records(data)["P11-FU-40"]["priority_disposition"] = "reviewed: no change"
    assert any("P11-FU-40" in p and "cannot be overridden" in p for p in _problems(tmp_path, data))


def test_conflicting_source_priorities_need_a_priority_disposition(tmp_path: Path) -> None:
    text = POOL.replace(
        "| Promoted -> [Plan 12.1](plan-12-1.md) | MEDIUM | Plan 12.1 | entry |\n\n",
        "| Promoted -> [Plan 12.1](plan-12-1.md) | HIGH | Plan 12.1 | entry |\n\n",
    )
    assert text != POOL  # only the P12-FU-1 row (the index's last row) now says HIGH
    data = _good()
    records = _records(data)
    records["P11.25-FU-1"].update(units=records["P11.25-FU-1"]["units"] + records["P12-FU-1"]["units"], duplicate_rationale="filed twice")
    data["records"] = [r for r in data["records"] if r["id"] != "P12-FU-1"]
    assert any("P11.25-FU-1" in p and "conflicting source priorities" in p for p in _problems(tmp_path, data, text))

    records["P11.25-FU-1"]["priority_disposition"] = "the entry's own row is authoritative (reviewed)"
    assert _problems(tmp_path, data, text) == []


def test_source_priority_cells_compare_case_insensitively(tmp_path: Path) -> None:
    text = POOL.replace(
        "| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |",
        "| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | medium |",
    )
    assert text != POOL
    assert _problems(tmp_path, _good(), text) == []


@pytest.mark.parametrize(
    ("target", "expected"),
    [
        (222, "already targets"),
        (0, "positive issue number"),
        (-1, "positive issue number"),
        ("224", "positive issue number"),
        (True, "positive issue number"),
    ],
)
def test_target_issues_are_positive_and_unique(tmp_path: Path, target: Any, expected: str) -> None:
    data = _good()
    _records(data)["P11-FU-40"]["target_issue"] = target  # plan:11.23 already targets #222
    assert any("P11-FU-40" in p and expected in p for p in _problems(tmp_path, data))


def test_only_a_migrating_record_targets_an_issue(tmp_path: Path) -> None:
    data = _good()
    _records(data)["A2A-M17"]["target_issue"] = 500
    assert any("A2A-M17" in p and "does not migrate" in p for p in _problems(tmp_path, data))


FROZEN_OWNERS = POOL + (
    "\n## Frozen approval bytes and live-status authority\n\n"
    "- `docs/superpowers/plans/archive/shared.md` — SHA-256 `" + "A" * 64 + "` — Frozen approval bytes — live status is owned by the"
    " consolidated open-work pool. Live owner: [`P11-FU-20`](#p11-fu-20-attach-catalog) and [`P11-FU-40`](#p11-fu-40-real-zed).\n"
    "- `docs/superpowers/plans/archive/plan.md` — SHA-256 `" + "B" * 64 + "` — Frozen approval bytes — live status is owned by the"
    " consolidated open-work pool. Live owner: [Plan 11.23 registry row](#live-implementation-plan-registry) and"
    " [`P9.96-FU-7` disposition](#closed-history).\n"
)


def _frozen() -> dict[str, Any]:
    data = _good()
    data["sections"].append(
        {"source": "pool", "title": "Frozen approval bytes and live-status authority", "classification": "migrated", "rationale": "owners"}
    )
    _records(data)["plan:11.23"]["aliases"] = ["Plan 11.23"]
    for name, related in (("shared", ["P11-FU-20", "P11-FU-40"]), ("plan", ["plan:11.23"])):
        data["records"].append(
            _record(
                id=f"frozen:{name}.md",
                kind="frozen-mapping",
                status=None,
                disposition="not-work",
                priority=None,
                units=[_unit(FROZEN_OWNERS, f"archive/{name}.md")],
                related=related,
            )
        )
    return data


def test_a_frozen_mapping_keeps_every_live_owner_that_has_a_record(tmp_path: Path) -> None:
    assert _problems(tmp_path, _frozen(), FROZEN_OWNERS) == []  # P9.96-FU-7 has no record, so it stays a name only
    for record_id, dropped in (("frozen:shared.md", "P11-FU-20"), ("frozen:shared.md", "P11-FU-40"), ("frozen:plan.md", "plan:11.23")):
        data = _frozen()
        _records(data)[record_id]["related"].remove(dropped)
        problems = _problems(tmp_path, data, FROZEN_OWNERS)
        assert any(record_id in p and dropped in p and "live owner" in p for p in problems), (record_id, dropped)


def test_owner_identities_are_every_identity_in_order_without_repeats() -> None:
    text = "[`P11-FU-18`](#p11-fu-18-x) and [`P11-FU-29`](#p11-fu-29-y); see `P11-FU-18` and [Plan 11.23](#z)."
    assert gwt.owner_identities(text) == ["P11-FU-18", "P11-FU-29", "Plan 11.23"]
    assert gwt.owner_identities(None) == []


# ---- the parser fails closed ----

UNKNOWN_STATUSES = ["Not started", "Pending", "In progress", "Deferred", "Unresolved", "TODO", "Partially closed"]
MISREAD_STATUSES = ["Disclosed; still Open", "Unblocked", "Reopened", "Already merged", "Openly tracked"]


@pytest.mark.parametrize("status", UNKNOWN_STATUSES + MISREAD_STATUSES)
def test_unknown_status_words_count_as_unresolved(status: str) -> None:
    (unit,) = gwt.source_units("pool", f"## S\n\n### P11-FU-90: x\n\n**Status:** {status}.\n")
    assert unit.status_class == "unknown"
    assert unit.unresolved


@pytest.mark.parametrize(
    ("text", "token"),
    [
        ("Open.", "open"),
        ("Promoted -> [Plan 12.1](x.md).", "promoted"),
        ("`Blocked`", "blocked"),
        ("~~Closed~~", "closed"),
        ("`ACCEPTED_OPEN`", "accepted_open"),
        ("`UNRUN_BINDING`", "unrun_binding"),
        ("Partially implemented. Plan 11.20 …", "partially implemented"),
        ("Not drafted", "not drafted"),
        ("Active", "active"),
        ("Complete (2026-07-11).", "complete"),
        ("Disclosed; still Open", None),
        ("Unblocked", None),
    ],
)
def test_status_tokens_are_leading_and_word_bounded(text: str, token: str | None) -> None:
    assert gwt.normalized_status(text) == token


@pytest.mark.parametrize("status", ["Promoted -> x", "Partially implemented", "Blocked", "Not drafted", "Active", "Ready", "In review"])
def test_each_open_token_is_unresolved_work(status: str) -> None:
    (unit,) = gwt.source_units("pool", f"## S\n\n| ID | Status |\n|---|---|\n| `P11-FU-91` | {status} |\n")
    assert unit.status_class == "unresolved"


def test_section_status_is_a_unit_even_next_to_entries() -> None:
    text = "## S\n\n**Status:** Open. Section-level work.\n\n### P11-FU-92: child\n\n**Status:** Closed.\n"
    units = gwt.source_units("pool", text)
    assert [(u.kind, u.status_class) for u in units] == [("section-record", "unresolved"), ("entry", "resolved")]


def test_partly_struck_row_is_reported_and_counts_as_open() -> None:
    scan = gwt.scan_source("pool", "## S\n\n| ID | Status |\n|---|---|\n| ~~`P11-FU-102`~~ | Open |\n| ~~`P11-FU-103`~~ | ~~Closed~~ |\n")
    first, second = scan.units
    assert first.status_class == "unknown" and second.status_class == "resolved"
    assert any("partly struck row" in a for a in scan.anomalies)


@pytest.mark.parametrize(
    "line",
    [
        "Status: Open",
        "- **Status:** Open",
        "**status:** Open",
        "**Status (2026-10-04):** Open",
        "**Status**: Open",
        "**Current status:** Open",
        "Status for pickup: **needs investigation**",
    ],
)
def test_loose_status_lines_are_reported(line: str) -> None:
    scan = gwt.scan_source("pool", f"## S\n\n### P11-FU-93: x\n\n{line}\n")
    assert any("unrecognized form" in a for a in scan.anomalies)
    assert scan.units[0].status_class == "unknown"


def test_prose_that_starts_with_status_is_not_a_status_line() -> None:
    scan = gwt.scan_source("pool", "## S\n\n- Status ownership follows exactly one chain: backlog then masterplan.\n")
    assert scan.anomalies == ()


def test_second_status_line_in_one_record_is_reported() -> None:
    scan = gwt.scan_source("pool", "## S\n\n### P11-FU-94: x\n\n**Status:** Closed.\n\n#### Later\n\n**Status:** Open.\n")
    assert any("second **Status:** line" in a for a in scan.anomalies)
    assert scan.units[0].stated_status == "Closed."  # the first status line is the record's; the second is only reported


def test_a_blank_line_ends_a_table() -> None:
    text = "## S\n\n| ID | Status |\n|---|---|\n| `P11-FU-1` | Open |\n\nA note with a | pipe that is not a row\n"
    assert [unit.identity for unit in gwt.source_units("pool", text)] == ["P11-FU-1"]


def test_row_identity_comes_from_the_first_two_cells_only() -> None:
    text = "## S\n\n| Thing | Note | Owner |\n|---|---|---|\n| widget | detail | `P11-FU-5` |\n"
    (unit,) = gwt.source_units("pool", text)
    assert unit.identity == "widget"


def test_statusless_rows_need_a_record_or_a_reviewed_section(tmp_path: Path) -> None:
    text = POOL + "\n## Reference\n\n| Item | Note |\n|---|---|\n| thing | detail |\n"
    data = _good()
    data["sections"].append({"source": "pool", "title": "Reference", "classification": "not-work", "rationale": "reference table"})
    assert any("no status; claim it or mark" in p for p in _problems(tmp_path, data, text))

    data["sections"][-1]["statusless_reviewed"] = True
    assert _problems(tmp_path, data, text) == []


def test_empty_status_cell_is_unknown() -> None:
    (unit,) = gwt.source_units("pool", "## S\n\n| ID | Status |\n|---|---|\n| `P11-FU-95` |  |\n")
    assert unit.status_class == "unknown"


def test_indented_and_pipeless_tables_are_read() -> None:
    indented = gwt.source_units("pool", "## S\n\n  | ID | Status |\n  |---|---|\n  | `P11-FU-96` | Open |\n")
    pipeless = gwt.source_units("pool", "## S\n\nID | Status\n--- | ---\n`P11-FU-97` | Open\n")
    assert [u.identity for u in indented] == ["P11-FU-96"]
    assert [u.identity for u in pipeless] == ["P11-FU-97"]


def test_unbalanced_fence_is_reported_and_indented_fence_is_not_a_fence() -> None:
    scan = gwt.scan_source("pool", "## S\n\n```\nhidden\n\n### P11-FU-98: x\n\n**Status:** Open.\n")
    assert any("never closed" in a for a in scan.anomalies)

    units = gwt.source_units("pool", "## S\n\n    ```\n    code\n\n### P11-FU-99: x\n\n**Status:** Open.\n")
    assert [u.identity for u in units] == ["P11-FU-99"]


def test_reviewed_anomalies_are_accepted_and_stale_ones_reported(tmp_path: Path) -> None:
    text = POOL + "Status for pickup: later.\n"  # appended, so no unit line moves
    data = _good()
    assert any("unreadable source" in p for p in _problems(tmp_path, data, text))

    data["reviewed_anomalies"] = {_unit(text, "Status for pickup"): "pickup note, not a lifecycle status"}
    assert _problems(tmp_path, data, text) == []

    data["reviewed_anomalies"] = {"pool:1": "stale"}
    assert any("no longer occurs" in p for p in _problems(tmp_path, data))


def test_short_obligation_codes_are_identities_only_as_a_whole_first_cell() -> None:
    text = (
        "## A\n\n| Kind | Identity | Disposition |\n|---|---|---|\n"
        "| Candidate C15 | `P11.26-CAND-1-RESOURCE-LIFETIME` | `ACCEPTED_OPEN` |\n\n"
        "## B\n\n| Obligation | Status |\n|---|---|\n| H12a | Open |\n"
    )
    assert [unit.identity for unit in gwt.source_units("pool", text)] == ["P11.26-CAND-1-RESOURCE-LIFETIME", "H12a"]


def test_identities_never_end_on_a_hyphen() -> None:
    (unit,) = gwt.source_units("pool", "## S\n\n| Note | Gate |\n|---|---|\n| the three `P11.26-UNRUN-*` gates | x |\n")
    assert not unit.identity.endswith("-")


def test_frozen_live_owner_mappings_are_not_status_lines() -> None:
    text = (
        "## Frozen approval bytes and live-status authority\n\n"
        "- `docs/superpowers/plans/archive/x.md` — SHA-256 `" + "A" * 64 + "` — Frozen approval bytes — live status is owned by "
        "the consolidated open-work pool. Live owner: Open item `P11-FU-4`.\n"
    )
    (unit,) = gwt.source_units("pool", text)
    assert unit.kind == "frozen-mapping" and unit.identity == "docs/superpowers/plans/archive/x.md"
    assert not unit.unresolved


def test_state_and_disposition_columns_carry_status() -> None:
    text = (
        "## Live implementation plan registry\n\n| Plan | State |\n|---|---|\n| [Plan 9.1 — x](x.md) | `Blocked` |\n\n"
        "## C\n\n| Identity | Disposition |\n|---|---|\n| `P11.26-UNRUN-ZED` | `UNRUN` |\n"
    )
    assert [u.status_class for u in gwt.source_units("pool", text)] == ["unresolved", "unresolved"]


# ---- every structural rule fires ----


def _rule_cases() -> list[tuple[str, Any, str]]:
    def drop_closed_record(data: dict[str, Any]) -> None:
        data["records"] = [r for r in data["records"] if r["id"] != "A2A-M17"]

    def classify_twice(data: dict[str, Any]) -> None:
        data["sections"].append(dict(data["sections"][0]))

    def unknown_classification(data: dict[str, Any]) -> None:
        data["sections"][0]["classification"] = "archived"

    def empty_rationale(data: dict[str, Any]) -> None:
        data["sections"][0]["rationale"] = " "

    def duplicate_record_id(data: dict[str, Any]) -> None:
        data["records"].append(dict(_records(data)["P11-FU-40"], units=[]))

    def foreign_unit(data: dict[str, Any]) -> None:
        _records(data)["P11-FU-40"]["units"].append("pool:9999")

    def set_field(record_id: str, **fields: Any) -> Any:
        return lambda data: _records(data)[record_id].update(fields)

    def duplicate_of_duplicate(data: dict[str, Any]) -> None:
        _records(data)["P12-FU-1"].update(disposition="duplicate", duplicate_of="P11.25-FU-1", duplicate_rationale="same")
        _records(data)["P11.25-FU-1"].update(disposition="duplicate", duplicate_of="P11-FU-40", duplicate_rationale="same")

    def alias_collision(data: dict[str, Any]) -> None:
        _records(data)["P11-FU-40"]["aliases"] = ["FU-X"]
        _records(data)["A2A-C1"]["aliases"] = ["FU-X"]

    def unknown_anchor_target(data: dict[str, Any]) -> None:
        data["compat_anchors"] = {"old-anchor": "NOPE"}

    def cycle(data: dict[str, Any]) -> None:
        _records(data)["plan:12.1"]["parent"] = "P12-FU-1"

    return [
        ("resolved row in a mixed section needs a record", drop_closed_record, "its section is not retired"),
        ("section classified twice", classify_twice, "classified twice"),
        ("unknown classification", unknown_classification, "unknown classification"),
        ("empty section rationale", empty_rationale, "has no rationale"),
        ("duplicate record id", duplicate_record_id, "is used twice"),
        ("claimed unit not in the sources", foreign_unit, "is not a unit of the sources"),
        ("unknown kind", set_field("P11-FU-40", kind="epic"), "unknown kind"),
        ("unknown disposition", set_field("P11-FU-40", disposition="parked"), "unknown disposition"),
        ("unknown product", set_field("A2A-C1", product="mars"), "unknown product"),
        ("record with no units", set_field("P11-FU-40", units=[]), "claims no source unit"),
        ("unknown parent", set_field("P11-FU-40", parent="NOPE"), "references unknown record"),
        (
            "unknown duplicate_of",
            set_field("P12-FU-1", disposition="duplicate", duplicate_of="NOPE", duplicate_rationale="x"),
            "unknown record",
        ),
        ("unknown related", set_field("P11-FU-40", related=["NOPE"]), "references unknown record"),
        ("duplicate without duplicate_of", set_field("P12-FU-1", disposition="duplicate", duplicate_rationale="x"), "without duplicate_of"),
        ("duplicate of a duplicate", duplicate_of_duplicate, "duplicate of another duplicate"),
        ("migrate without a title", set_field("P11-FU-40", title=" "), "without a title"),
        ("reviewed without a note", set_field("P11-FU-40", reviewed=True), "without a review note"),
        ("retired parent", set_field("P11-FU-40", parent="A2A-M17"), "not migrating"),
        ("parent cycle", cycle, "parent cycle"),
        ("alias names two records", alias_collision, "names both"),
        ("compatibility anchor to an unknown record", unknown_anchor_target, "compatibility anchor"),
    ]


@pytest.mark.parametrize(("name", "mutate", "expected"), _rule_cases(), ids=[case[0] for case in _rule_cases()])
def test_each_structural_rule_fires(tmp_path: Path, name: str, mutate: Any, expected: str) -> None:
    data = _good()
    mutate(data)
    assert any(expected in p for p in _problems(tmp_path, data)), name


def test_external_issue_records_need_no_source_unit(tmp_path: Path) -> None:
    data = _good()
    data["records"].append(
        _record(
            id="issue:33",
            kind="external-issue",
            status="Open",
            status_disposition="the existing issue's GitHub state; no source unit states it",
            disposition="migrate",
            units=[],
            target_issue=33,
        )
    )
    assert _problems(tmp_path, data) == []


def test_load_rejects_unknown_schema_and_unknown_fields(tmp_path: Path) -> None:
    data = copy.deepcopy(_good())
    data["schema"] = "something-else"
    with pytest.raises(ValueError, match="schema"):
        gwt.load_inventory(_write(tmp_path, data))
    data = _good()
    _records(data)["P11-FU-40"]["surprise"] = True
    with pytest.raises(ValueError, match="unknown fields"):
        gwt.load_inventory(_write(tmp_path, data))


def test_source_bytes_must_match_the_inventory_baseline(tmp_path: Path) -> None:
    changed = POOL.replace("Real Zed containment", "Real Zed containment v2")
    report = gwt.validate_inventory(gwt.load_inventory(_write(tmp_path, _good())), {"pool": changed.encode()})
    assert any("pool" in p and "baseline" in p for p in report.problems)


def test_every_unit_is_claimed_at_most_once(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["P11-FU-40"]["units"].append(records["A2A-C1"]["units"][0])
    assert any("claimed by more than one record" in p for p in _problems(tmp_path, data))


# ---- the named program fixtures: tracks board and MAIN-5 residuals ----


def test_tracks_and_main5_residuals(tmp_path: Path) -> None:
    u = lambda needle: _unit(PROGRAM, needle)  # noqa: E731 - local fixture shorthand
    data = {
        "schema": gwt.SCHEMA,
        "baseline": {"commit": "fixture", "sources": {"pool": {"path": "p.md", "blob": gwt.git_blob_id(PROGRAM.encode())}}},
        "sections": [
            {"source": "pool", "title": "Child-plan status board", "classification": "migrated", "rationale": "tracks"},
            {"source": "pool", "title": "MAIN-5 residuals under existing 11.x owners", "classification": "mixed", "rationale": "residuals"},
        ],
        "records": [
            _record(id="HARDENING-TRACK-RUFF-LINT", kind="track", status="Not drafted", disposition="migrate", units=[u("RUFF-LINT`")]),
            _record(id="HARDENING-TRACK-CI-GUARDRAILS", kind="track", status="Active", disposition="migrate", units=[u("CI-GUARDRAILS`")]),
            _record(id="P11-FU-31", kind="follow-up", status="Open.", disposition="migrate", units=[u("### P11-FU-31")]),
            _record(id="P11-FU-33", kind="follow-up", status="Closed. Through PR #219.", disposition="history", units=[u("### P11-FU-33")]),
        ],
    }
    report = gwt.validate_inventory(gwt.load_inventory(_write(tmp_path, data)), {"pool": PROGRAM.encode()})
    assert report.problems == ()

    _records(data)["P11-FU-31"]["units"].append(u("CI-GUARDRAILS`"))
    data["records"] = [r for r in data["records"] if r["id"] != "HARDENING-TRACK-CI-GUARDRAILS"]
    report = gwt.validate_inventory(gwt.load_inventory(_write(tmp_path, data)), {"pool": PROGRAM.encode()})
    assert any("plan and item" in p for p in report.problems)


# ---- git and pins ----


def test_git_blob_id_is_gits_algorithm() -> None:
    assert gwt.git_blob_id(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"  # pragma: allowlist secret - git's empty blob id
    assert gwt.git_blob_id(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"  # pragma: allowlist secret - git blob id of "hello\n"


def test_sources_are_read_from_a_commit_not_the_working_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def git(*args: str) -> None:
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q")
    (repo / "f.md").write_bytes(b"committed\n")
    git("add", "f.md")
    git("commit", "-q", "-m", "c")
    (repo / "f.md").write_bytes(b"working tree\n")
    assert gwt.read_sources_at("HEAD", {"x": "f.md"}, repo) == {"x": b"committed\n"}


# ---- drafting rules ----


def test_owner_cells_that_coordinate_or_defer_give_no_parent() -> None:
    records = [
        rules._record(id="P11-FU-4", kind="follow-up", status="Open", units=["pool:5"]),
        rules._record(id="P11-FEAT-ZED-RESUME", kind="feature", status="Open", units=["pool:9"]),
    ]
    text = (
        "## Follow-up status index\n\n| ID | Item | Status | Owning slice / designated plan |\n|---|---|---|---|\n"
        "| `P11-FU-4` | Re-pin | Open | Coordinated with `P11-FEAT-ZED-RESUME` |\n\n"
        "## Feature slices\n\n| Identity | Status |\n|---|---|\n| `P11-FEAT-ZED-RESUME` | Open |\n"
    )
    scans = {
        "pool": gwt.scan_source("pool", text),
        "masterplan": gwt.scan_source("masterplan", ""),
        "roadmap": gwt.scan_source("roadmap", ""),
    }
    rules._derive(records, scans)
    assert records[0]["parent"] is None
    assert records[0]["related"] == ["P11-FEAT-ZED-RESUME"]


def test_draft_links_frozen_owners_by_record_id_or_alias() -> None:
    records = [
        rules._record(id="plan:11.23", kind="plan", status="Blocked", aliases=["Plan 11.23"]),
        rules._record(id="P11-FU-18", kind="follow-up", status="Closed", disposition="history", aliases=["P11-FU-18"]),
        rules._record(id="frozen:x.md", kind="frozen-mapping", disposition="not-work", related=["P11-FU-18", "Plan 11.23", "P9.96-FU-7"]),
    ]
    empty = {name: gwt.scan_source(name, "") for name in rules.SOURCES}
    rules._derive(records, empty)
    assert records[2]["related"] == ["P11-FU-18", "plan:11.23"]  # P9.96-FU-7 has no record, so it stays a name only


def test_draft_refuses_an_unreviewed_section() -> None:
    with pytest.raises(ValueError, match="no reviewed classification"):
        rules.classify("pool", "A section nobody reviewed")


def test_committed_manifest_validates_at_its_baseline() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    report = gwt.validate_inventory(inventory, gwt.read_sources_at(inventory.baseline_commit, inventory.source_paths))
    assert report.problems == ()
    assert report.counts["migrate"] > 0


def test_draft_reproduces_the_committed_manifest_byte_for_byte() -> None:
    commit = json.loads(MANIFEST.read_text(encoding="utf-8"))["baseline"]["commit"]
    drafted = gwt.render_manifest(rules.draft_inventory(commit, gwt.read_sources_at(commit, rules.SOURCES)))
    assert drafted.encode("utf-8") == MANIFEST.read_bytes()


def test_reviewed_overrides_are_marked_in_the_manifest() -> None:
    records = {r["id"]: r for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]}
    for record_id in rules.OVERRIDES:
        assert records[record_id]["reviewed"] is True and records[record_id]["review_note"]


def test_the_shared_fu18_fu29_design_keeps_both_owner_links() -> None:
    records = {r["id"]: r for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]}
    shared = records["frozen:2026-08-15-p11-fu-18-29-durable-approval-workspace-identity-design.md"]
    assert shared["related"] == ["P11-FU-18", "P11-FU-29"]
    assert {records[owner]["disposition"] for owner in shared["related"]} == {"history"}  # history references, not new issues


def test_issue_33_is_reconciled_read_only_and_keeps_its_p0_source() -> None:
    issue = {r["id"]: r for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]}["issue:33"]
    note = issue["review_note"]
    assert "read-only" in note and "reports/plan-9-75-zed-hitl-runtime-evidence.md" in note
    assert "P11-FEAT-ZED-RESUME" in note and "no Zed" in note  # a new reproduction belongs to the Zed owner's lane
    assert "reproduction attempt" not in note
    assert issue["priority"] == "HIGH" and "P0" in issue["priority_disposition"]
    assert issue["status"] == "Open" and issue["status_disposition"] and issue["target_issue"] == 33


# ---- CLI ----


def test_cli_validate_reports_problems_with_a_nonzero_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "A2A-C1"]
    path = _write(tmp_path, data)
    reader = lambda commit, paths: {"pool": POOL.encode("utf-8")}  # noqa: E731 - fixture reader
    assert gwt.main(["validate", str(path)], reader=reader) == 1
    assert "unclaimed unit" in capsys.readouterr().out

    _write(tmp_path, _good())
    assert gwt.main(["validate", str(path)], reader=reader) == 0


def test_cli_draft_writes_the_manifest_bytes(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    commit = json.loads(MANIFEST.read_text(encoding="utf-8"))["baseline"]["commit"]
    assert gwt.main(["draft", commit]) == 0
    assert capsysbinary.readouterr().out == MANIFEST.read_bytes()
