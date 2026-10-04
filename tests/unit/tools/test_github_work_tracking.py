"""Plan 11.29 work-tracking migration: inventory coverage, fail-closed parsing and drafting rules."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import re
import subprocess
from collections.abc import Sequence
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


# ==== Task 2: bounded, restart-safe publication and reconciliation ====


def _api() -> str:
    """The REST path prefix of the repository (resolved at call time)."""
    return f"repos/{gwt.REPO}/"


# The 13 labels the pilot published on 2026-10-03 (publication evidence seal 7a789680): name -> (description, color).
PILOT_LABELS = {
    "shadow-pilot": ("Trial copy; repository pool remains authoritative", "d4c5f9"),
    "status:open": ("Source record is Open", "0e8a16"),
    "status:blocked": ("Source record is Blocked", "d93f0b"),
    "status:partially-implemented": ("Source record is Partially implemented", "fbca04"),
    "priority:medium": ("Medium scheduling priority", "fbca04"),
    "difficulty:medium": ("Medium complexity/difficulty; default unless assessed", "c2e0c6"),
    "estimate:na": ("Planned Estimate is NA: not estimated", "ededed"),
    "handler:unassigned": ("No current work handler assigned", "ededed"),
    "product:optimus": ("Optimus product", "1d76db"),
    "product:evidence-a2a": ("Evidence/A2A product", "5319e7"),
    "kind:plan": ("Tracking issue for a repository implementation plan", "0052cc"),
    "kind:follow-up": ("Deferred follow-up with its own acceptance criteria", "006b75"),
    "kind:obligation": ("Audit obligation retaining its owning feature custody", "7057ff"),
}
PILOT_DEFAULTS = ["shadow-pilot", "priority:medium", "difficulty:medium", "estimate:na", "handler:unassigned", "product:optimus"]


def _label(name: str) -> dict[str, str]:
    return {"name": name, "color": "ededed", "description": ""}


def _issue(
    number: int,
    *,
    body: str = "",
    title: str = "t",
    labels: Sequence[str] = (),
    state: str = "open",
    parent: int | None = None,
    pr: bool = False,
) -> dict[str, Any]:
    """An issue as GitHub's REST issue-list and issue endpoints return it."""
    issue: dict[str, Any] = {
        "number": number,
        "id": 900_000 + number,
        "title": title,
        "body": body,
        "labels": [_label(name) for name in labels],
        "state": state,
        "state_reason": "completed" if state == "closed" else None,
        "html_url": f"https://github.com/{gwt.REPO}/issues/{number}",
        "parent_issue_url": f"https://api.github.com/repos/{gwt.REPO}/issues/{parent}" if parent else None,
    }
    if pr:
        issue["pull_request"] = {"url": f"https://api.github.com/repos/{gwt.REPO}/pulls/{number}"}
    return issue


def _pilot_issues() -> list[dict[str, Any]]:
    """The pilot's #222 (Plan 11.23) and #223 (P11-FU-20, native child of #222), with their source markers."""
    return [
        _issue(
            222,
            title="Plan 11.23: Client-MCP runtime composition",
            body="> trial copy\n\n<!-- optimus-source: PLAN-11.23 -->\n\npilot body\n<!-- /optimus-source: PLAN-11.23 -->\n",
            labels=[*PILOT_DEFAULTS, "status:blocked", "kind:plan"],
        ),
        _issue(
            223,
            title="P11-FU-20: Attach catalog",
            body="<!-- optimus-source: P11-FU-20 -->\n\npilot body\n<!-- /optimus-source: P11-FU-20 -->\n\nOperator note.\n",
            labels=[*PILOT_DEFAULTS, "status:partially-implemented", "kind:follow-up"],
            parent=222,
        ),
    ]


def _pilot_labels() -> list[dict[str, str]]:
    return [{"name": name, "description": description, "color": color} for name, (description, color) in PILOT_LABELS.items()]


class FakeGitHub:
    """GitHub REST transport double: raw JSON text in the documented response shapes, plus faults.

    Parsing, planning, validation, journaling and stop handling are the module's own code; only the transport is
    replaced. ``faults`` maps a write's index (in send order) to a callable that receives the object GitHub would
    apply and return, and may alter it or raise before anything is applied; or to ``"lost"`` (applied, but the
    response never arrives), ``"malformed"`` (applied; the response is not JSON), ``"no-parent-link"`` or
    ``"no-sub-list"`` (a sub-issue binding GitHub only half records).
    """

    def __init__(self, issues: Sequence[dict[str, Any]] = (), labels: Sequence[dict[str, str]] = ()) -> None:
        self.issues = {issue["number"]: copy.deepcopy(issue) for issue in issues}
        self.labels = {label["name"]: dict(label) for label in labels}
        self.subs: dict[int, list[int]] = {}
        for issue in self.issues.values():
            if issue["parent_issue_url"]:
                self.subs.setdefault(int(issue["parent_issue_url"].rsplit("/", 1)[1]), []).append(issue["number"])
        self.log: list[tuple[str, str]] = []
        self.writes: list[tuple[str, str, dict[str, Any]]] = []
        self.faults: dict[int, Any] = {}
        self.next_number, self.next_id = 300, 7000

    @staticmethod
    def _page(items: list[Any], path: str) -> str:
        query = dict(part.split("=", 1) for part in path.split("?", 1)[1].split("&"))
        size, page = int(query["per_page"]), int(query["page"])
        return json.dumps(items[(page - 1) * size : page * size])

    def get(self, path: str) -> str:
        self.log.append(("GET", path))
        rest = path.removeprefix(_api())
        if rest.startswith("issues?"):
            return self._page([self.issues[number] for number in sorted(self.issues)], rest)
        if rest.startswith("labels?"):
            return self._page(list(self.labels.values()), rest)
        parts = rest.split("?", 1)[0].split("/")
        number = int(parts[1])
        if len(parts) == 2:
            return json.dumps(self.issues[number])
        if parts[2] == "sub_issues":
            return self._page([self.issues[child] for child in self.subs.get(number, [])], rest)
        if parts[2] == "parent":
            url = self.issues[number]["parent_issue_url"]
            if url is None:
                raise gwt.TransportError("gh: No parent issue found (HTTP 404)", status=404)
            return json.dumps(self.issues[int(url.rsplit("/", 1)[1])])
        raise AssertionError(f"unexpected GET {path}")

    def send(self, method: str, path: str, payload: dict[str, Any]) -> str:
        index = len(self.writes)
        self.log.append((method, path))
        self.writes.append((method, path, copy.deepcopy(payload)))
        fault = self.faults.get(index)
        rest = path.removeprefix(_api())
        if (method, rest) == ("POST", "labels"):
            obj: dict[str, Any] = {"id": self._id(), **payload}
        elif (method, rest) == ("POST", "issues"):
            obj = _issue(self.next_number, title=payload["title"], body=payload["body"], labels=payload["labels"])
            obj["id"] = self._id()
            self.next_number += 1
        elif method == "PATCH" and rest.startswith("issues/"):
            obj = copy.deepcopy(self.issues[int(rest.split("/")[1])])
            obj.update(title=payload["title"], body=payload["body"], labels=[_label(name) for name in payload["labels"]])
        elif method == "POST" and rest.endswith("/sub_issues"):
            parent = int(rest.split("/")[1])
            child = next(issue for issue in self.issues.values() if issue["id"] == payload["sub_issue_id"])
            obj = copy.deepcopy(self.issues[parent])
        else:
            raise AssertionError(f"unexpected {method} {path}")
        if callable(fault):
            obj = fault(obj)
        if rest == "labels":
            self.labels[obj["name"]] = obj
        elif rest.endswith("/sub_issues"):
            if fault != "no-sub-list":
                self.subs.setdefault(parent, []).append(child["number"])
            if fault != "no-parent-link":
                child["parent_issue_url"] = f"https://api.github.com/repos/{gwt.REPO}/issues/{parent}"
        else:
            self.issues[obj["number"]] = obj
        if fault == "lost":
            raise gwt.TransportError("timed out waiting for the response")
        return "<html>502 Bad Gateway</html>" if fault == "malformed" else json.dumps(obj)

    def _id(self) -> int:
        self.next_id += 1
        return self.next_id


def _setup(
    tmp_path: Path,
    data: dict[str, Any] | None = None,
    text: str = POOL,
    issues: Sequence[dict[str, Any]] | None = None,
    labels: Sequence[dict[str, str]] | None = None,
) -> tuple[gwt.Inventory, list[gwt.IssueDraft], FakeGitHub]:
    inventory = gwt.load_inventory(_write(tmp_path, _with_source(data or _good(), text)))
    drafts = gwt.draft_issues(inventory, {"pool": text.encode("utf-8")})
    client = FakeGitHub(_pilot_issues() if issues is None else issues, _pilot_labels() if labels is None else labels)
    return inventory, drafts, client


def _plan(inventory: gwt.Inventory, drafts: list[gwt.IssueDraft], client: FakeGitHub) -> gwt.MigrationBatch:
    return gwt.plan_migration(inventory, drafts, gwt.read_issues(client), gwt.read_labels(client))


def _publish(
    tmp_path: Path, batch: gwt.MigrationBatch, client: FakeGitHub, name: str = "journal.jsonl"
) -> tuple[gwt.PublicationResult, list[dict[str, Any]]]:
    path = tmp_path / name
    result = gwt.publish_batch(batch, client, gwt.Journal(path), pause=lambda: None)
    return result, [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _at(batch: gwt.MigrationBatch, op: str) -> int:
    """The index of the first operation of a kind; each operation is exactly one write, so it is also the write index."""
    return next(index for index, operation in enumerate(batch.operations) if operation.op == op)


def test_all_pages_and_pr_exclusion(tmp_path: Path) -> None:
    filler = [_issue(number, pr=number % 10 == 0) for number in range(1000, 1250)]
    pr_with_marker = _issue(1300, pr=True, body="<!-- optimus-source: P11-FU-40 -->")
    labels = _pilot_labels() + [_label(f"other:{number}") for number in range(120)]
    inventory, drafts, client = _setup(tmp_path, issues=[*_pilot_issues(), *filler, pr_with_marker], labels=labels)

    issues = gwt.read_issues(client)
    assert sorted(issue.number for issue in issues) == [222, 223, *(n for n in range(1000, 1250) if n % 10)]
    pages = [path for method, path in client.log if path.startswith(_api() + "issues?")]
    assert pages == [f"{_api()}issues?state=all&per_page=100&page={page}" for page in (1, 2, 3, 4)]
    assert len(gwt.read_labels(client)) == 133
    assert sum(path.startswith(_api() + "labels?") for _method, path in client.log) == 3

    batch = _plan(inventory, drafts, client)  # a marker inside a pull request is not an issue identity
    assert batch.conflicts == ()
    assert any(op.op == "create-issue" and op.target == "P11-FU-40" for op in batch.operations)


def test_issue_snapshots_validate_parent_urls_and_fingerprint_metadata() -> None:
    issue = gwt.issue_snapshot(_issue(223, body="<!-- optimus-source: P11-FU-20 -->", labels=["b", "a"], parent=222))
    assert (issue.parent, issue.labels, issue.markers) == (222, ("a", "b"), ("P11-FU-20",))
    assert (
        issue.fingerprint
        != gwt.issue_snapshot(_issue(223, body="<!-- optimus-source: P11-FU-20 -->", labels=["a"], parent=222)).fingerprint
    )
    foreign = _issue(5) | {"parent_issue_url": "https://api.github.com/repos/someone/else/issues/9"}
    with pytest.raises(gwt.ReadFailed, match="parent"):
        gwt.issue_snapshot(foreign)


@pytest.mark.parametrize("fault", ["timeout", "lost", "malformed"])
def test_unknown_create_outcome_stops_without_retry(tmp_path: Path, fault: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    first = _at(batch, "create-issue")

    def timeout(_obj: dict[str, Any]) -> dict[str, Any]:
        raise gwt.TransportError("timed out before GitHub applied anything")

    client.faults[first] = timeout if fault == "timeout" else fault
    result, journal = _publish(tmp_path, batch, client)

    assert result.outcome == "unknown" and "not retried" in result.reason
    assert len(client.writes) == first + 1  # one attempt for it, and nothing after it
    intent = [record for record in journal if record["step"] == "intent"][-1]
    assert (intent["op"], intent["target"]) == ("create-issue", batch.operations[first].target)
    assert intent["payload_sha256"] == batch.operations[first].payload_sha256
    assert journal[-1]["step"] == "outcome" and journal[-1]["outcome"] == "unknown"
    assert journal.index(intent) == len(journal) - 2  # the intent was durable before the write was sent

    client.faults = {}
    replan = _plan(inventory, drafts, client)
    if fault == "timeout":
        assert replan.conflicts == ()  # nothing was applied, so a fresh plan may create it again under fresh authority
        return
    assert any("no reviewed target issue" in conflict for conflict in replan.conflicts)
    writes = len(client.writes)
    result, _journal = _publish(tmp_path, replan, client, name="rerun.jsonl")
    assert result.outcome == "refused" and len(client.writes) == writes


def test_marker_hit_reuses_reviewed_pilot_identity(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    assert batch.conflicts == ()
    assert {record_id: ref.number for record_id, ref in batch.reused.items()} == {"plan:11.23": 222, "P11-FU-20": 223}
    assert not {"plan:11.23", "P11-FU-20"} & {op.target for op in batch.operations if op.op == "create-issue"}
    assert {op.issue for op in batch.operations if op.op == "update-issue"} == {222, 223}
    assert not [op for op in batch.operations if op.op == "bind-sub-issue" and op.payload["child"] == "P11-FU-20"]  # already bound

    without_marker = _pilot_issues()
    without_marker[0]["body"] = "pilot body without its marker"
    closed = _pilot_issues()
    closed[0].update(state="closed", state_reason="completed")
    reparented = _pilot_issues()  # #223 bound under some other issue
    reparented[1]["parent_issue_url"] = f"https://api.github.com/repos/{gwt.REPO}/issues/500"
    parented = _pilot_issues()  # #222's record has no parent, but the issue has one
    parented[0]["parent_issue_url"] = f"https://api.github.com/repos/{gwt.REPO}/issues/500"
    cases = {
        "does not carry its source marker": without_marker,
        "more than one issue": [*_pilot_issues(), _issue(500, body="<!-- optimus-source: PLAN-11.23 -->")],
        "is closed": closed,
        "does not exist": _pilot_issues()[1:],
        "no migrating record owns": [*_pilot_issues(), _issue(501, body="<!-- optimus-source: P11-FU-999 -->")],
        "already a native sub-issue of #500": [*reparented, _issue(500)],
        "has no parent, but #222": [*parented, _issue(500)],
    }
    for expected, issues in cases.items():
        conflicts = _plan(inventory, drafts, FakeGitHub(issues, _pilot_labels())).conflicts
        assert any(expected in conflict for conflict in conflicts), (expected, conflicts)


@pytest.mark.parametrize("case", ["repository label differs", "two values in one dimension", "unknown value in a dimension"])
def test_conflicting_labels_prevent_first_write(tmp_path: Path, case: str) -> None:
    labels, issues = _pilot_labels(), _pilot_issues()
    if case == "repository label differs":
        labels = [dict(label, color="ffffff") if label["name"] == "status:open" else label for label in labels]
    elif case == "two values in one dimension":
        issues[0]["labels"].append(_label("priority:high"))
    else:  # the issue's only handler label has a value the vocabulary does not know
        issues[1]["labels"] = [
            _label("handler:somebody") if label["name"] == "handler:unassigned" else label for label in issues[1]["labels"]
        ]
    inventory, drafts, client = _setup(tmp_path, issues=issues, labels=labels)

    batch = _plan(inventory, drafts, client)
    assert batch.conflicts
    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "refused" and client.writes == []
    assert [record["step"] for record in journal] == ["start", "outcome"]


def test_identical_existing_labels_are_reused(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    assert [op.target for op in batch.operations if op.op == "create-label"] == ["status:promoted"]
    assert batch.operations[0].payload == {"name": "status:promoted", **gwt.LABEL_SPECS["status:promoted"].payload()}


@pytest.mark.parametrize("edit", ["body", "labels"])
def test_concurrent_body_or_label_edit_blocks_update(tmp_path: Path, edit: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    update = _at(batch, "update-issue")
    target = batch.operations[update].issue
    if edit == "body":
        client.issues[target]["body"] += "\n\nEdited after the plan was read."
    else:
        client.issues[target]["labels"].append(_label("handler:codex"))

    result, _journal = _publish(tmp_path, batch, client)
    assert result.outcome == "failed" and "concurrent" in result.reason
    assert len(client.writes) == update  # every earlier write happened; this update and everything after it did not
    assert not any(path.endswith(f"issues/{target}") for _method, path, _payload in client.writes)


@pytest.mark.parametrize("fault", [None, "no-parent-link", "no-sub-list"])
def test_required_parent_binding_verified_both_ways(tmp_path: Path, fault: str | None) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    bind = _at(batch, "bind-sub-issue")
    if fault:
        client.faults[bind] = fault

    result, _journal = _publish(tmp_path, batch, client)
    operation = batch.operations[bind]
    child, parent = result.issues[operation.payload["child"]], result.issues[operation.payload["parent"]]
    if fault is None:
        assert result.outcome == "pass"
        position = client.log.index(("POST", f"{_api()}issues/{parent}/sub_issues"))
        later = [path for method, path in client.log[position + 1 :] if method == "GET"]
        assert f"{_api()}issues/{child}/parent" in later
        assert f"{_api()}issues/{parent}/sub_issues?per_page=100&page=1" in later
    else:
        assert result.outcome == "failed" and len(client.writes) == bind + 1
        assert ("parent" if fault == "no-parent-link" else "sub-issues") in result.reason


@pytest.mark.parametrize("op", ["create-label", "create-issue", "update-issue"])
def test_write_result_mismatch_blocks_next_write(tmp_path: Path, op: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    index = _at(batch, op)
    client.faults[index] = {
        "create-label": lambda obj: dict(obj, color="000000"),
        "create-issue": lambda obj: dict(obj, body=obj["body"] + "\naltered"),
        "update-issue": lambda obj: dict(obj, title="changed by GitHub"),
    }[op]

    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "failed" and "differs from the request" in result.reason
    assert len(client.writes) == index + 1
    if op != "create-label":  # the observed identity stays on record for reconciliation
        assert [record for record in journal if record["step"] == "result"][-1]["number"]


def test_metadata_defaults_preserve_explicit_values(tmp_path: Path) -> None:
    text = POOL.replace(
        "| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | MEDIUM |",
        "| C1 | CRITICAL | `EVIDENCE-HANDOFF-FEAT-LEDGER-COMPOSITION` | Open | HIGH |",
    )
    data = _good()
    _records(data)["A2A-C1"]["priority"] = "HIGH"
    issues = _pilot_issues()
    explicit = ["priority:low", "difficulty:high", "handler:claude", "needs-operator"]
    issues[0]["labels"] = [_label(name) for name in ["shadow-pilot", "status:blocked", "kind:plan", "product:optimus", *explicit]]
    inventory, drafts, client = _setup(tmp_path, data, text, issues=issues)

    by_id = {draft.record_id: draft for draft in drafts}
    assert {"priority:medium", "difficulty:medium", "estimate:na", "handler:unassigned"} <= set(by_id["plan:12.1"].labels)
    assert "priority:high" in by_id["A2A-C1"].labels and "priority:medium" not in by_id["A2A-C1"].labels
    update = next(op for op in _plan(inventory, drafts, client).operations if op.issue == 222)
    assert set(update.payload["labels"]) == {*explicit, "estimate:na", "status:blocked", "kind:plan", "product:optimus", "shadow-pilot"}

    # An explicit source priority never silently replaces, or is replaced by, a different explicit label.
    issues = _pilot_issues()
    issues[1]["labels"] = [label for label in issues[1]["labels"] if label["name"] != "priority:medium"] + [_label("priority:high")]
    inventory, drafts, client = _setup(tmp_path, issues=issues)
    assert any("P11-FU-20" in conflict and "priority" in conflict for conflict in _plan(inventory, drafts, client).conflicts)


def test_migration_reconciliation_exact_coverage(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    result, _journal = _publish(tmp_path, _plan(inventory, drafts, client), client)
    assert result.outcome == "pass"
    report = gwt.reconcile(inventory, drafts, gwt.read_issues(client))
    assert report.problems == () and report.ok
    assert report.mapping == result.issues and len(report.mapping) == 8 == len(set(report.mapping.values()))
    numbers = result.issues

    def broken(change: Any) -> list[str]:
        issues = copy.deepcopy(client.issues)
        change(issues)
        return list(gwt.reconcile(inventory, drafts, gwt.read_issues(FakeGitHub(list(issues.values())))).problems)

    def relabel(record_id: str, old: str, new: str | None) -> Any:
        def change(issues: dict[int, Any]) -> None:
            issue = issues[numbers[record_id]]
            issue["labels"] = [_label(new) if label["name"] == old else label for label in issue["labels"] if new or label["name"] != old]

        return change

    def moved_marker(issues: dict[int, Any]) -> None:  # the plan's marker now sits on a new issue, not on its reviewed #222
        issues[902] = _issue(
            902, title=issues[222]["title"], body=issues[222]["body"], labels=[label["name"] for label in issues[222]["labels"]]
        )
        issues[222]["body"] = "marker removed"

    def shared(issues: dict[int, Any]) -> None:  # one issue carries two records' markers
        issues[numbers["H4"]]["body"] += "\n<!-- optimus-source: P11-FU-40 -->"
        issues[numbers["P11-FU-40"]]["body"] = "marker removed"

    cases = {
        "has no issue": lambda issues: issues.pop(numbers["P11-FU-40"]),
        "more than one issue": lambda issues: issues.update({900: _issue(900, body="<!-- optimus-source: P11-FU-40 -->")}),
        "no migrating record owns": lambda issues: issues.update({901: _issue(901, body="<!-- optimus-source: P11-FU-999 -->")}),
        "status labels": relabel("A2A-C1", "status:open", "status:blocked"),
        "native parent": lambda issues: issues[numbers["P12-FU-1"]].update(parent_issue_url=None),
        "generated region differs": lambda issues: issues[numbers["H4"]].update(
            body=issues[numbers["H4"]]["body"].replace("Source status", "Edited status")
        ),
        "title differs": lambda issues: issues[numbers["P12-FU-1"]].update(title="renamed"),
        "closed": lambda issues: issues[numbers["plan:12.1"]].update(state="closed", state_reason="completed"),
        "not its reviewed target #222": moved_marker,
        "lacks the shadow-pilot label": relabel("P11-FU-40", "shadow-pilot", None),
        "exactly one valid difficulty label": relabel("A2A-C1", "difficulty:medium", None),
        "not its source priority": relabel("P11-FU-40", "priority:medium", "priority:low"),
        "mapped by more than one record": shared,
        "exactly one valid priority label": lambda issues: issues[numbers["A2A-C1"]]["labels"].append(_label("Priority:High")),
        "no generated region": lambda issues: issues[numbers["H4"]].update(
            body=issues[numbers["H4"]]["body"].replace("<!-- /optimus-source: H4 -->", "")
        ),
    }
    for expected, change in cases.items():
        problems = broken(change)
        assert any(expected in problem for problem in problems), (expected, problems)


# ---- issue bodies quote the pinned source exactly ----


def test_bodies_quote_each_claimed_unit_with_baseline_permalinks(tmp_path: Path) -> None:
    _inventory, drafts, _client = _setup(tmp_path)
    by_id = {draft.record_id: draft for draft in drafts}
    plan = by_id["plan:11.23"]
    assert plan.title == _records(_good())["plan:11.23"]["title"]  # the record's reviewed title
    assert plan.body.startswith("<!-- optimus-source: PLAN-11.23 -->\n") and plan.body.count("<!-- optimus-source:") == 1
    base = f"https://github.com/{gwt.REPO}/blob/fixture/"
    promoted = f"**Source status at baseline `fixture`:** Promoted -> [Plan 12.1]({base}plan-12-1.md) (historical"
    assert promoted in by_id["P11.25-FU-1"].body  # a status quoted in the facts is pinned like the source text
    assert (
        "| Plan | State | Backlog owner | Next gate |\n|---|---|---|---|\n"
        f"| [Plan 11.23 — client-MCP runtime composition]({base}plan-11-23.md) | `Blocked` | `P11-FU-20` | Task 6 live gate. |"
    ) in plan.body
    assert f"{base}pool.md?plain=1#L{_unit(POOL, '[Plan 11.23').split(':')[1]}" in plan.body

    item = by_id["P11-FU-20"].body
    assert "### P11-FU-20: Attach catalog\n\n**Status:** Partially implemented. Live Plan 11.23 supersedes the production residual." in item
    assert "| `P11-FU-20` | Attach catalog | Partially implemented | MEDIUM | Live blocked Plan 11.23 Task 6 | report |" in item
    assert "Source status at baseline `fixture`" in item


def test_unit_text_is_the_unit_alone_without_trailing_blank_lines() -> None:
    text = "## S\n\n**Status:** Open. Section work.\n\n### P11-FU-92: child\n\n**Status:** Closed.\n\n\n## T\n"
    section, entry = gwt.source_units("pool", text)
    lines = text.splitlines()
    assert gwt.unit_source_text(section, lines) == "## S\n\n**Status:** Open. Section work."  # not the entries beneath it
    assert gwt.unit_source_text(entry, lines) == "### P11-FU-92: child\n\n**Status:** Closed."


def test_a_label_without_a_reviewed_spec_is_a_conflict(tmp_path: Path) -> None:
    text = POOL.replace("| Real Zed containment | Open |", "| Real Zed containment | Deferred |").replace(
        "### P11-FU-40: Real Zed containment\n\n**Status:** Open.", "### P11-FU-40: Real Zed containment\n\n**Status:** Deferred."
    )
    data = _good()
    _records(data)["P11-FU-40"]["status"] = "Deferred"
    inventory, drafts, client = _setup(tmp_path, data, text)
    conflicts = _plan(inventory, drafts, client).conflicts
    assert any("status:unrecognized" in conflict and "no reviewed specification" in conflict for conflict in conflicts)


def test_only_link_targets_change_when_source_is_quoted() -> None:
    text = "See [plan](../plans/x.md#task-2), [here](#anchor), [web](https://example.com/a) and ![img](img.png)."
    base = f"https://github.com/{gwt.REPO}/blob/abc/docs/superpowers/"
    assert gwt.normalize_links(text, "docs/superpowers/plans/pool.md", "abc") == (
        f"See [plan]({base}plans/x.md#task-2), [here]({base}plans/pool.md#anchor), [web](https://example.com/a)"
        f" and ![img]({base}plans/img.png)."
    )
    with pytest.raises(ValueError, match="outside the repository"):
        gwt.normalize_links("[x](../../../etc.md)", "docs/a.md", "abc")


def test_every_real_body_quotes_its_claimed_units_exactly() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    sources = gwt.read_sources_at(inventory.baseline_commit, inventory.source_paths)
    drafts = gwt.draft_issues(inventory, sources)
    records = {r.id: r for r in inventory.records if r.disposition == "migrate"}
    assert {draft.record_id for draft in drafts} == {rid for rid, record in records.items() if record.kind != "external-issue"}
    units = {unit.key: unit for name, data in sources.items() for unit in gwt.scan_source(name, data.decode("utf-8")).units}
    lines = {name: data.decode("utf-8").splitlines() for name, data in sources.items()}
    for draft in drafts:
        for key in records[draft.record_id].units:
            unit = units[key]
            quoted = gwt.unit_source_text(unit, lines[unit.source])
            linked = gwt.normalize_links(quoted, inventory.source_paths[unit.source], inventory.baseline_commit)
            assert linked in draft.body, key
            assert re.sub(r"\]\([^)]*\)", "]()", linked) == re.sub(r"\]\([^)]*\)", "]()", quoted), key
        targets = re.findall(r"\]\(([^)\s]*)\)", draft.body)
        assert all(target.startswith(("https://", "mailto:")) for target in targets), draft.record_id
        assert len(draft.body) <= 65_536 and 0 < len(draft.title) <= 256 and "{{" not in draft.body
        assert draft.body.count("<!-- optimus-source:") == 1, draft.record_id


@pytest.mark.parametrize(
    ("record_id", "marker"),
    [
        ("plan:11.23", "PLAN-11.23"),
        ("P11-FU-20", "P11-FU-20"),
        ("P11-FU-40", "P11-FU-40"),
        ("A2A-C1", "EVIDENCE-HANDOFF-A2A-C1"),
        ("feature:plan-12", "feature:plan-12"),
        ("plan:evidence-collector", "PLAN-evidence-collector"),
    ],
)
def test_source_markers_follow_the_pilot(record_id: str, marker: str) -> None:
    assert gwt.source_marker(record_id) == marker


def test_label_specs_match_the_pilot_and_the_page_vocabulary() -> None:
    for name, (description, color) in PILOT_LABELS.items():
        assert gwt.LABEL_SPECS[name] == gwt.LabelSpec(name, description, color)
    vocabulary = gwt.page_vocabulary()
    expected = {"shadow-pilot", *(f"status:{s}" for s in vocabulary["statuses"]), *(f"product:{p}" for p in vocabulary["products"])}
    expected |= {f"kind:{kind}" for kind in vocabulary["kinds"]}
    for dimension in vocabulary["dimensions"].values():
        expected |= {f"{dimension['label']}:{value}" for value in dimension["values"]}
    assert set(gwt.LABEL_SPECS) == expected
    assert all(re.fullmatch(r"[0-9a-f]{6}", spec.color) and spec.description for spec in gwt.LABEL_SPECS.values())


@pytest.mark.parametrize(("state", "expected"), [("open", None), ("closed", "is closed"), (None, "does not exist")])
def test_an_external_issue_is_reconciled_without_any_write(tmp_path: Path, state: str | None, expected: str | None) -> None:
    data = _good()
    data["records"].append(
        _record(
            id="issue:33",
            kind="external-issue",
            status="Open",
            status_disposition="the existing issue's GitHub state",
            disposition="migrate",
            units=[],
            target_issue=33,
        )
    )
    issues = _pilot_issues() + ([_issue(33, title="P0: Zed hangs", state=state)] if state else [])
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)

    batch = _plan(inventory, drafts, client)
    assert not [op for op in batch.operations if "issue:33" in op.target]
    if expected is None:
        assert batch.conflicts == () and batch.reused["issue:33"].number == 33
    else:
        assert any("issue:33" in conflict and expected in conflict for conflict in batch.conflicts)


def test_cli_plan_is_read_only_and_publish_runs_only_the_reviewed_batch(tmp_path: Path) -> None:
    path = _write(tmp_path, _with_source(_good(), POOL))
    reader = lambda commit, paths: {"pool": POOL.encode("utf-8")}  # noqa: E731 - fixture reader
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    batch_path = tmp_path / "batch.json"

    assert gwt.main(["plan", str(path), "--out", str(batch_path)], reader=reader, client=client) == 0
    assert client.writes == []
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    assert batch["schema"] == gwt.SCHEMA and batch["conflicts"] == []
    assert batch["budget"]["writes"] == len(batch["operations"]) == 11

    def publish(evidence: str, *extra: str) -> int:
        argv = ["publish", str(path), "--batch", str(batch_path), "--evidence-dir", str(tmp_path / evidence), "--pause-seconds", "0"]
        return gwt.main([*argv, *extra], reader=reader, client=client)

    assert publish("no-execute") == 2 and client.writes == []
    client.issues[222]["body"] += "\nedited after review"
    assert publish("stale", "--execute") == 2 and client.writes == []  # a fresh plan must equal the reviewed batch
    client.issues[222]["body"] = client.issues[222]["body"].removesuffix("\nedited after review")
    assert publish("run", "--execute") == 0 and len(client.writes) == 11
    assert (tmp_path / "run" / "journal.jsonl").is_file() and (tmp_path / "run" / "batch.json").read_bytes() == batch_path.read_bytes()
    seal = (tmp_path / "run" / "evidence.sha256").read_text(encoding="utf-8").splitlines()
    names = ("batch.json", "journal.jsonl")
    assert seal == [f"{hashlib.sha256((tmp_path / 'run' / name).read_bytes()).hexdigest()}  {name}" for name in names]


def test_gh_client_classifies_transport_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(["gh"], 1, b"", b"gh: Not Found (HTTP 404)")

    monkeypatch.setattr(gwt.subprocess, "run", failing)
    with pytest.raises(gwt.TransportError) as error:
        gwt.GhClient().get("repos/x/y/issues/1/parent")
    assert error.value.status == 404

    def slow(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired("gh", 120)

    monkeypatch.setattr(gwt.subprocess, "run", slow)
    with pytest.raises(gwt.TransportError, match="TimeoutExpired"):
        gwt.GhClient().send("POST", "repos/x/y/issues", {"title": "t"})

    calls: list[Any] = []

    def ok(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        calls.append((command, kwargs.get("input")))
        return subprocess.CompletedProcess(command, 0, b'{"number": 1}', b"")

    monkeypatch.setattr(gwt.subprocess, "run", ok)
    assert gwt.GhClient().send("PATCH", "repos/x/y/issues/1", {"title": "t"}) == '{"number": 1}'
    assert calls == [(["gh", "api", "-X", "PATCH", "repos/x/y/issues/1", "--input", "-"], b'{"title": "t"}')]


# ---- Checkpoint 2 review: reused bodies, own markers, label case, duplicate list objects, binding faults ----


def test_an_update_rewrites_only_the_generated_region_and_keeps_the_title(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    regions = {draft.record_id: draft.body for draft in drafts}
    assert regions["plan:11.23"].endswith("<!-- /optimus-source: PLAN-11.23 -->\n")
    updates = {op.issue: op.payload for op in _plan(inventory, drafts, client).operations if op.op == "update-issue"}
    assert updates[222]["title"] == "Plan 11.23: Client-MCP runtime composition"  # an existing title is never rewritten
    assert updates[222]["body"] == "> trial copy\n\n" + regions["plan:11.23"]  # text before the region survives
    assert updates[223]["body"] == regions["P11-FU-20"] + "\nOperator note.\n"  # and text after it


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("> trial copy\n\n<!-- optimus-source: PLAN-11.23 -->\n\nCodex-drafted pilot body", "no generated region"),
        ("<!-- /optimus-source: PLAN-11.23 -->\n<!-- optimus-source: PLAN-11.23 -->\n", "malformed generated region"),
    ],
)
def test_a_body_without_a_well_formed_generated_region_is_a_conflict(tmp_path: Path, body: str, expected: str) -> None:
    issues = _pilot_issues()
    issues[0]["body"] = body
    inventory, drafts, client = _setup(tmp_path, issues=issues)
    batch = _plan(inventory, drafts, client)
    assert any("plan:11.23" in conflict and expected in conflict for conflict in batch.conflicts), batch.conflicts
    assert not [op for op in batch.operations if op.issue == 222]


@pytest.mark.parametrize("literal", ["<!-- optimus-source: P11-FU-20 -->", "<!-- /optimus-source: P11-FU-40 -->"])
def test_a_body_must_carry_exactly_its_own_markers(tmp_path: Path, literal: str) -> None:
    entry = "### P11-FU-40: Real Zed containment\n\n**Status:** Open.\n"
    text = POOL.replace(entry, entry.replace("Open.", f"Open. Quoted: `{literal}`."))  # same line count, so unit keys hold
    assert text != POOL
    inventory, drafts, client = _setup(tmp_path, text=text)
    conflicts = _plan(inventory, drafts, client).conflicts
    assert any("P11-FU-40" in conflict and "exactly its own markers" in conflict for conflict in conflicts), conflicts


def test_label_names_compare_case_insensitively(tmp_path: Path) -> None:
    labels = [*_pilot_labels(), {"name": "Status:Promoted", **gwt.LABEL_SPECS["status:promoted"].payload()}]
    inventory, drafts, client = _setup(tmp_path, labels=labels)
    batch = _plan(inventory, drafts, client)
    assert not [op for op in batch.operations if op.op == "create-label"]  # GitHub would refuse the case-variant name
    assert any("'Status:Promoted'" in conflict for conflict in batch.conflicts), batch.conflicts

    issues = _pilot_issues()
    issues[0]["labels"].append(_label("Priority:High"))
    inventory, drafts, client = _setup(tmp_path, issues=issues)
    assert any("Priority:High" in conflict for conflict in _plan(inventory, drafts, client).conflicts)

    issues = _pilot_issues()  # a case variant of a source-dimension label is managed, so the update replaces it
    issues[0]["labels"] = [_label("Status:Blocked") if label["name"] == "status:blocked" else label for label in issues[0]["labels"]]
    inventory, drafts, client = _setup(tmp_path, issues=issues)
    update = next(op for op in _plan(inventory, drafts, client).operations if op.issue == 222)
    assert "Status:Blocked" not in update.payload["labels"] and "status:blocked" in update.payload["labels"]


def test_generated_region_needs_exactly_one_start_and_one_end_in_order() -> None:
    start, end = "<!-- optimus-source: X -->", "<!-- /optimus-source: X -->"
    assert gwt.generated_region(f"a\n{start}\nb\n{end}\nc", "X") == (2, 2 + len(f"{start}\nb\n{end}"))
    assert "2 copies" in str(gwt.generated_region(f"{start}\n{start}\n{end}", "X"))
    assert "no generated region" in str(gwt.generated_region(f"{start}\nb", "X"))
    assert "malformed" in str(gwt.generated_region(f"{end}\n{start}", "X"))
    assert "malformed" in str(gwt.generated_region(f"{start}\n{end}\n{end}", "X"))


class _Pages:
    """A read-only list endpoint that serves fixed pages, then an empty one."""

    def __init__(self, pages: list[list[Any]]) -> None:
        self.pages = pages

    def get(self, path: str) -> str:
        page = int(path.rsplit("page=", 1)[1])
        return json.dumps(self.pages[page - 1] if page <= len(self.pages) else [])


def test_an_object_listed_twice_is_read_once() -> None:
    first, second = _pilot_issues()
    assert [issue.number for issue in gwt.read_issues(_Pages([[first, second], [first]]))] == [222, 223]
    label = _pilot_labels()[0]
    assert list(gwt.read_labels(_Pages([[label, label]]))) == [label["name"]]


@pytest.mark.parametrize("fault", ["timeout", "lost"])
def test_unknown_binding_outcome_stops_without_retry(tmp_path: Path, fault: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    bind = _at(batch, "bind-sub-issue")

    def timeout(_obj: dict[str, Any]) -> dict[str, Any]:
        raise gwt.TransportError("timed out before GitHub applied anything")

    client.faults[bind] = timeout if fault == "timeout" else fault
    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "unknown" and len(client.writes) == bind + 1
    assert journal[-2]["step"] == "intent" and journal[-2]["op"] == "bind-sub-issue"


# ---- Checkpoint 2 Codex review: unexpected failures always end with an outcome; bodies hold no current metadata ----


class _FailingJournal(gwt.Journal):
    """A journal whose storage fails at one step."""

    def __init__(self, path: Path | None, failing_step: str) -> None:
        super().__init__(path)
        self.failing_step = failing_step

    def write(self, step: str, **fields: Any) -> None:
        if step == self.failing_step:
            raise OSError("the evidence disk is unavailable")
        super().write(step, **fields)


def _explode(_obj: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError("the transport crashed")


def _publish_cli(tmp_path: Path, client: FakeGitHub, evidence: str, *extra: str) -> int:
    path = _write(tmp_path, _with_source(_good(), POOL))
    reader = lambda commit, paths: {"pool": POOL.encode("utf-8")}  # noqa: E731 - fixture reader
    batch_path = tmp_path / "batch.json"
    if not batch_path.exists():
        assert gwt.main(["plan", str(path), "--out", str(batch_path)], reader=reader, client=client) == 0
    argv = ["publish", str(path), "--batch", str(batch_path), "--evidence-dir", str(tmp_path / evidence), *extra]
    return gwt.main(argv, reader=reader, client=client)


@pytest.mark.parametrize("which", ["the first write", "a write after a created issue"])
def test_an_unexpected_error_during_a_write_is_an_unknown_outcome(tmp_path: Path, which: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    creates = [index for index, op in enumerate(batch.operations) if op.op == "create-issue"]
    index = 0 if which == "the first write" else creates[1]
    client.faults[index] = _explode

    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "unknown" and "RuntimeError" in result.reason and "not retried" in result.reason
    assert len(client.writes) == index + 1  # no retry and no later write
    assert journal[-1]["step"] == "outcome" and journal[-1]["outcome"] == "unknown"
    if index:
        first = batch.operations[creates[0]].target
        assert result.issues[first] == journal[-1]["issues"][first]  # a created identity is kept on record


def test_an_unexpected_error_while_verifying_a_binding_is_an_unknown_outcome(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    bind = _at(batch, "bind-sub-issue")
    read = client.get

    def get(path: str) -> str:
        if path.endswith("/parent"):
            raise RuntimeError("the response decoder crashed")
        return read(path)

    client.get = get  # type: ignore[method-assign]
    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "unknown" and len(client.writes) == bind + 1
    assert journal[-1]["outcome"] == "unknown"


def test_an_unexpected_error_before_a_write_sends_nothing_for_it(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    update = _at(batch, "update-issue")
    target = batch.operations[update].issue
    read = client.get

    def get(path: str) -> str:
        if path.endswith(f"issues/{target}"):
            raise RuntimeError("the response decoder crashed")
        return read(path)

    client.get = get  # type: ignore[method-assign]
    result, journal = _publish(tmp_path, batch, client)
    assert result.outcome == "failed" and "nothing was written for it" in result.reason
    assert len(client.writes) == update and journal[-1]["outcome"] == "failed"


@pytest.mark.parametrize(
    ("step", "outcome", "sent"), [("start", "failed", 0), ("intent", "failed", 0), ("result", "unknown", 1), ("validated", "failed", 1)]
)
def test_an_unwritable_journal_stops_the_run_and_says_so(tmp_path: Path, step: str, outcome: str, sent: int) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    result = gwt.publish_batch(batch, client, _FailingJournal(tmp_path / "journal.jsonl", step), pause=lambda: None)
    assert result.outcome == outcome and result.journal_ok is False
    assert len(client.writes) == sent  # an intent that cannot be recorded is never sent


@pytest.mark.parametrize(("step", "operations"), [("start", 0), ("validated", 1)])
def test_a_journal_failure_is_never_a_pass(tmp_path: Path, step: str, operations: int) -> None:
    # Where no later journal record follows (an empty batch, or the last operation), the failure itself must stop the run.
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    batch = dataclasses.replace(batch, operations=batch.operations[:operations])
    result = gwt.publish_batch(batch, client, _FailingJournal(tmp_path / "journal.jsonl", step), pause=lambda: None)
    assert result.outcome == "failed" and result.journal_ok is False


def test_cli_publish_seals_its_evidence_after_an_unexpected_error(tmp_path: Path) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    _publish_cli(tmp_path, client, "warmup", "--pause-seconds", "0")  # no --execute: plans the batch only
    client.faults[2] = _explode
    assert _publish_cli(tmp_path, client, "run", "--pause-seconds", "0", "--execute") == 3
    assert len(client.writes) == 3
    evidence = tmp_path / "run"
    journal = [json.loads(line) for line in (evidence / "journal.jsonl").read_text(encoding="utf-8").splitlines()]
    assert journal[-1]["outcome"] == "unknown"
    seal = (evidence / "evidence.sha256").read_text(encoding="utf-8").splitlines()
    assert seal == [f"{hashlib.sha256((evidence / name).read_bytes()).hexdigest()}  {name}" for name in ("batch.json", "journal.jsonl")]


def test_cli_publish_never_claims_a_seal_it_could_not_make(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    _publish_cli(tmp_path, client, "warmup", "--pause-seconds", "0")
    monkeypatch.setattr(gwt, "Journal", lambda path: _FailingJournal(path, "intent"))
    assert _publish_cli(tmp_path, client, "run", "--pause-seconds", "0", "--execute") == 1
    assert client.writes == [] and not (tmp_path / "run" / "evidence.sha256").exists()
    assert "could not be sealed" in capsys.readouterr().out


@pytest.mark.parametrize("pause", ["-1", "nan", "inf"])
def test_cli_publish_rejects_an_invalid_pause_before_any_request(tmp_path: Path, pause: str) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    (tmp_path / "batch.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        _publish_cli(tmp_path, client, "run", "--pause-seconds", pause, "--execute")
    assert client.log == [] and not (tmp_path / "run").exists()


def test_bodies_state_no_current_metadata(tmp_path: Path) -> None:
    issues = _pilot_issues()
    explicit = ["priority:low", "difficulty:high", "estimate:3d", "handler:claude"]
    issues[0]["labels"] = [_label(name) for name in ["shadow-pilot", "status:blocked", "kind:plan", "product:optimus", *explicit]]
    data = _good()
    _records(data)["A2A-C1"]["severity"] = "CRITICAL"  # as the drafting rules set it from the obligation row
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    batch = _plan(inventory, drafts, client)
    assert batch.conflicts == ()
    assert set(explicit) <= set(next(op for op in batch.operations if op.issue == 222).payload["labels"])
    for draft in drafts:
        for current in ("**Priority:**", "**Difficulty:**", "**Planned Estimate:**", "**Handler:**", "**Severity:**"):
            assert current not in draft.body, (draft.record_id, current)
        assert "labels carry the current values" in draft.body, draft.record_id
    assert "**Source severity:** CRITICAL" in {draft.record_id: draft for draft in drafts}["A2A-C1"].body


def test_a_metadata_only_label_change_needs_no_body_update(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    result, _journal = _publish(tmp_path, _plan(inventory, drafts, client), client)
    assert result.outcome == "pass"
    for old, new in (("handler:unassigned", "handler:claude"), ("difficulty:medium", "difficulty:high")):
        client.issues[222]["labels"] = [_label(new) if label["name"] == old else label for label in client.issues[222]["labels"]]
    assert not [op for op in _plan(inventory, drafts, client).operations if op.issue == 222]
    assert gwt.reconcile(inventory, drafts, gwt.read_issues(client)).problems == ()
    for current in ("**Handler:**", "**Difficulty:**"):
        assert current not in client.issues[222]["body"]
