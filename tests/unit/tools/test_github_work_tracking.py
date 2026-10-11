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
    report = gwt.validate_inventory(inventory, gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths))
    assert report.problems == ()
    assert report.counts["migrate"] > 0


def test_draft_reproduces_the_committed_manifest_byte_for_byte() -> None:
    commit = json.loads(MANIFEST.read_text(encoding="utf-8"))["baseline"]["commit"]
    drafted = rules.draft_inventory(commit, gwt.read_sources_at(commit, rules.READS), gwt.read_plans_at(commit))
    committed = gwt.load_inventory(MANIFEST).records
    if all(r.target_issue is not None for r in committed if r.disposition == "migrate"):  # finalized after publication
        drafted = gwt.finalize_inventory(drafted, {r.id: r.target_issue for r in committed if r.target_issue is not None})
    assert gwt.render_manifest(drafted).encode("utf-8") == MANIFEST.read_bytes()


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
    drafted = rules.draft_inventory(commit, gwt.read_sources_at(commit, rules.READS), gwt.read_plans_at(commit))
    assert capsysbinary.readouterr().out == gwt.render_manifest(drafted).encode("utf-8")


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
    promoted = "**Source status at baseline `fixture`:** Promoted (the leading status of the source quoted below; historical"
    assert promoted in by_id["P11.25-FU-1"].body  # the facts name the status; the quoted source carries its links
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
    sources = gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths)
    drafts = gwt.draft_issues(inventory, sources)
    records = {r.id: r for r in inventory.records if r.disposition == "migrate"}
    assert {draft.record_id for draft in drafts} == {rid for rid, record in records.items() if record.kind != "external-issue"}
    coverage = {name: sources[name] for name in inventory.source_paths}
    units = {unit.key: unit for name, data in coverage.items() for unit in gwt.scan_source(name, data.decode("utf-8")).units}
    lines = {name: data.decode("utf-8").splitlines() for name, data in coverage.items()}
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


# ---- Checkpoint 2 Codex follow-up at 700155e: a run whose required evidence is incomplete never reports success ----


class _SealBlockedJournal(gwt.Journal):
    """A journal that records every step, after which the evidence seal cannot be stored (its path is taken)."""

    def write(self, step: str, **fields: Any) -> None:
        super().write(step, **fields)
        if step == "outcome" and self.path is not None:
            (self.path.parent / "evidence.sha256").mkdir()


def _journal_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _created_on_record(journal: list[dict[str, Any]]) -> dict[str, int]:
    """The issue each create produced, as its durable result record states it."""
    return {record["target"]: record["number"] for record in journal if record["step"] == "result" and record["op"] == "create-issue"}


@pytest.mark.parametrize("operations", [None, 0], ids=["a normal batch", "an empty batch"])
def test_an_unjournaled_final_outcome_is_never_a_pass(tmp_path: Path, operations: int | None) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    batch = dataclasses.replace(batch, operations=batch.operations[:operations])
    path = tmp_path / "journal.jsonl"
    result = gwt.publish_batch(batch, client, _FailingJournal(path, "outcome"), pause=lambda: None)

    assert result.outcome == "incomplete" and result.journal_ok is False
    assert "applied and validated" in result.reason  # every write was validated, and that fact is kept
    assert "final outcome could not be journaled" in result.reason  # and no outcome record is claimed
    assert result.writes == len(client.writes) == len(batch.operations)  # no retry and no later write
    journal = _journal_lines(path)
    assert journal[-1]["step"] == ("validated" if batch.operations else "start")
    created = _created_on_record(journal)
    assert len(created) == sum(operation.op == "create-issue" for operation in batch.operations)
    assert dict(result.issues) == {**{record_id: ref.number for record_id, ref in batch.reused.items()}, **created}


@pytest.mark.parametrize("cause", ["unknown", "failed"])
def test_an_unjournaled_final_outcome_keeps_a_failed_or_unknown_classification(tmp_path: Path, cause: str) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    if cause == "unknown":
        stop = _at(batch, "create-issue") + 1
        client.faults[stop - 1] = "lost"
    else:
        stop = _at(batch, "update-issue")
        target, read = batch.operations[stop].issue, client.get

        def get(path: str) -> str:
            if path.endswith(f"issues/{target}"):
                raise RuntimeError("the response decoder crashed")
            return read(path)

        client.get = get  # type: ignore[method-assign]
    result = gwt.publish_batch(batch, client, _FailingJournal(tmp_path / "journal.jsonl", "outcome"), pause=lambda: None)
    assert result.outcome == cause and result.journal_ok is False
    assert "final outcome could not be journaled" in result.reason
    assert result.writes == len(client.writes) == stop  # no retry and no later write


def test_a_journal_failure_before_the_end_still_records_the_final_outcome(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    batch = _plan(inventory, drafts, client)
    path = tmp_path / "journal.jsonl"
    result = gwt.publish_batch(batch, client, _FailingJournal(path, "intent"), pause=lambda: None)
    journal = _journal_lines(path)
    assert result.outcome == "failed" and result.journal_ok is False
    assert journal[-1]["step"] == "outcome" and journal[-1]["outcome"] == "failed"
    assert "final outcome could not be journaled" not in result.reason  # it was; only the intent was not


def _publish_cli_summary(tmp_path: Path, client: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any]]:
    _publish_cli(tmp_path, client, "warmup", "--pause-seconds", "0")  # no --execute: plans the batch only
    capsys.readouterr()
    code = _publish_cli(tmp_path, client, "run", "--pause-seconds", "0", "--execute")
    return code, json.loads(capsys.readouterr().out.splitlines()[-1])


def test_cli_publish_with_an_unjournaled_final_outcome_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    monkeypatch.setattr(gwt, "Journal", lambda path: _FailingJournal(path, "outcome"))
    code, summary = _publish_cli_summary(tmp_path, client, capsys)

    assert code == 4 and summary["outcome"] == "incomplete" and summary["sealed"] is False
    assert summary["evidence"].startswith("incomplete") and "journal could not be written in full" in summary["evidence"]
    assert summary["writes"] == len(client.writes) == 11 and "applied and validated" in summary["reason"]
    evidence = tmp_path / "run"
    assert not (evidence / "evidence.sha256").exists()
    journal = _journal_lines(evidence / "journal.jsonl")
    assert journal[-1]["step"] == "validated"  # there is no outcome record, and none is claimed
    created = _created_on_record(journal)
    assert created and created.items() <= summary["issues"].items()  # known identities are kept


def test_cli_publish_whose_seal_cannot_be_written_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    monkeypatch.setattr(gwt, "Journal", _SealBlockedJournal)
    code, summary = _publish_cli_summary(tmp_path, client, capsys)

    assert code == 4 and summary["outcome"] == "incomplete" and summary["sealed"] is False
    assert summary["evidence"].startswith("incomplete") and "seal could not be written" in summary["evidence"]
    assert summary["writes"] == len(client.writes) == 11 and "applied and validated" in summary["reason"]
    evidence = tmp_path / "run"
    assert (evidence / "evidence.sha256").is_dir()  # the blocked path: no seal file exists
    journal = _journal_lines(evidence / "journal.jsonl")
    assert journal[-1]["step"] == "outcome" and journal[-1]["outcome"] == "pass"  # every write validated, on record
    assert summary["issues"] == journal[-1]["issues"]


# ==== Task 4: staged issue content (titles, reviewed context quotes, pilot adoption, the status fact) ====

CONTEXT_DOC = """\
# Context plan

**Goal:** Make the fixture plan usable.

## Tasks

Some tasks.

## Definition of Done

| Claim | Evidence |
|---|---|
| done | [proof](proof.md) |

### Detail

Nested detail stays inside the section.

## Self-review

Not quoted.
"""


def _context_inventory(tmp_path: Path, quotes: list[tuple[str, str, str]], pinned: str = CONTEXT_DOC) -> gwt.Inventory:
    data = _with_source(_good(), POOL)
    data["baseline"]["context"] = {"ctx": {"path": "docs/plans/ctx-plan.md", "blob": gwt.git_blob_id(pinned.encode("utf-8"))}}
    _records(data)["plan:11.23"]["quotes"] = [list(quote) for quote in quotes]
    return gwt.load_inventory(_write(tmp_path, data))


def _read(context: str = CONTEXT_DOC) -> dict[str, bytes]:
    return {"pool": POOL.encode("utf-8"), "ctx": context.encode("utf-8")}


def test_a_reviewed_context_quote_is_rendered_exactly_and_pinned(tmp_path: Path) -> None:
    inventory = _context_inventory(tmp_path, [("ctx", "line", "**Goal:**"), ("ctx", "section", "Definition of Done")])
    assert inventory.read_paths == {"pool": "pool.md", "ctx": "docs/plans/ctx-plan.md"}
    assert gwt.validate_inventory(inventory, _read()).problems == ()
    body = {draft.record_id: draft.body for draft in gwt.draft_issues(inventory, _read())}["plan:11.23"]
    base = gwt.blob_url("docs/plans/ctx-plan.md", "fixture")
    assert "**Goal:** Make the fixture plan usable." in body
    section = "\n".join(CONTEXT_DOC.splitlines()[8:17]).replace("(proof.md)", f"({gwt.blob_url('docs/plans/proof.md', 'fixture')})")
    assert section in body  # the heading through its nested detail, with the relative link pinned
    assert "Not quoted." not in body and "Some tasks." not in body
    assert f"({base}?plain=1#L3)" in body and f"({base}?plain=1#L9-L17)" in body
    assert body.index("**Goal:**") < body.index("## Definition of Done") < body.index("<!-- /optimus-source: PLAN-11.23 -->")


@pytest.mark.parametrize(
    ("quotes", "context", "expected"),
    [
        ([("ctx", "section", "Definition of Done")], CONTEXT_DOC.replace("Some tasks.", "Some tasks!"), "is not its pinned blob"),
        ([("ctx", "section", "Missing heading")], CONTEXT_DOC, "matches no"),
        ([("ctx", "section", "Detail")], CONTEXT_DOC + "\n### Detail\n\nAgain.\n", "matches 2"),
        ([("ctx", "line", "**Goal:**")], CONTEXT_DOC + "\n**Goal:** a second goal.\n", "matches 2"),
        ([("other", "line", "**Goal:**")], CONTEXT_DOC, "unknown context source"),
        ([("ctx", "paragraph", "**Goal:**")], CONTEXT_DOC, "unknown selector"),
    ],
)
def test_a_context_quote_must_resolve_exactly_once_at_its_pinned_blob(
    tmp_path: Path, quotes: list[tuple[str, str, str]], context: str, expected: str
) -> None:
    pinned = CONTEXT_DOC if expected == "is not its pinned blob" else context
    problems = gwt.validate_inventory(_context_inventory(tmp_path, quotes, pinned), _read(context)).problems
    assert any(expected in problem for problem in problems), problems


def test_the_real_pilot_context_quotes_keep_the_reviewed_passages() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    sources = gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths)
    drafts = {draft.record_id: draft.body for draft in gwt.draft_issues(inventory, sources)}
    assert {record.id for record in inventory.records if record.quotes} == {"plan:11.23", "A2A-C1"}
    plan = sources["plan-11-23"].decode("utf-8").splitlines()
    goal = next(line for line in plan if line.startswith("**Goal:**"))
    assert goal in drafts["plan:11.23"] and "## Definition of Done and Evidence Map" in drafts["plan:11.23"]
    audit = sources["a2a-audit"].decode("utf-8")
    assert "### Critical 1 — No shipped composition root or runbook can provision the claimed product" in drafts["A2A-C1"]
    root_cause = next(line for line in audit.splitlines() if line.startswith("**Root cause:** tested components"))
    assert root_cause in drafts["A2A-C1"] and "### Critical 2" not in drafts["A2A-C1"]


def test_no_migrating_record_keeps_a_bare_identifier_title() -> None:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))["records"]
    bare = [r["id"] for r in records if r["disposition"] == "migrate" and r["title"] in (r["id"], f"A2A obligation {r['id'][4:]}")]
    assert bare == []
    titled = {r["id"]: r["title"] for r in records}
    for record_id, phrase in rules.TITLES.items():
        assert 0 < len(phrase) <= 120 and titled[record_id] == f"{record_id}: {phrase}", record_id


def test_a2a_titles_are_the_audit_finding_headings() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    audit = gwt.git_blob_bytes(data["baseline"]["commit"], rules.CONTEXT["a2a-audit"]).decode("utf-8")
    headings = {(rank, number): text for rank, number, text in re.findall(r"^### (Critical|High|Medium) (\d+) — (.+)$", audit, re.M)}
    a2a = [r for r in data["records"] if r["id"].startswith("A2A-") and r["disposition"] == "migrate"]
    assert len(a2a) == 19
    for record in a2a:
        code = record["id"][4:]
        rank = {"C": "Critical", "H": "High", "M": "Medium"}[code[0]]
        number = re.match(r"[CHM](\d+)", code).group(1)
        assert record["title"] == f"A2A {code}: {headings[(rank, number)]}", record["id"]
    assert {r["id"]: r["title"] for r in a2a}[
        "A2A-C1"
    ] == "A2A C1: No shipped composition root or runbook can provision the claimed product"


def _legacy_pilot_issues() -> list[dict[str, Any]]:
    """The live pilots' shape: the source marker, but no generated region end."""
    issues = _pilot_issues()
    issues[0]["body"] = "> trial copy\n\n<!-- optimus-source: PLAN-11.23 -->\n\nCodex-drafted pilot body\n"
    return issues


def _adopt(data: dict[str, Any], record_id: str, issue: int, fingerprint: str) -> dict[str, Any]:
    """A reviewed adoption: the live issue's fingerprint at review, on one line with its secret-scan pin."""
    data.setdefault("adoptions", {})[record_id] = {"issue": issue, "fingerprint": fingerprint, "pin": rules.ADOPTION_PIN_NOTE}
    return data


def test_a_pilot_body_is_adopted_whole_only_at_its_reviewed_fingerprint(tmp_path: Path) -> None:
    issues = _legacy_pilot_issues()
    fingerprint = gwt.issue_snapshot(issues[0]).fingerprint
    data = _adopt(_good(), "plan:11.23", 222, fingerprint)
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    batch = _plan(inventory, drafts, client)
    assert batch.conflicts == ()
    update = next(op for op in batch.operations if op.issue == 222)
    region = {draft.record_id: draft.body for draft in drafts}["plan:11.23"].rstrip("\n")
    assert update.payload["body"] == region  # the whole reviewed pilot body is replaced by the generated region
    assert update.payload["title"] == issues[0]["title"] and update.expected_fingerprint == fingerprint
    result, _journal = _publish(tmp_path, batch, client)
    assert result.outcome == "pass"
    again = _plan(inventory, drafts, client)  # once adopted it has a region: nothing more to write for it, and no conflict
    assert not [c for c in again.conflicts if "plan:11.23" in c] and not [op for op in again.operations if op.issue == 222]


@pytest.mark.parametrize("case", ["edited after its review", "never reviewed for adoption", "malformed fingerprint"])
def test_an_unreviewed_or_changed_pilot_body_stays_a_conflict(tmp_path: Path, case: str) -> None:
    issues = _legacy_pilot_issues()
    data = _good()
    if case == "edited after its review":
        _adopt(data, "plan:11.23", 222, gwt.issue_snapshot(issues[0]).fingerprint)
        issues[0]["body"] += "\nedited after the review\n"
    if case == "malformed fingerprint":
        _adopt(data, "plan:11.23", 222, "not-a-digest")
        assert any("plan:11.23" in problem and "adoption" in problem for problem in _problems(tmp_path, data))
        return
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    batch = _plan(inventory, drafts, client)
    expected = "changed since its reviewed adoption" if case == "edited after its review" else "no generated region"
    assert any("plan:11.23" in conflict and expected in conflict for conflict in batch.conflicts), batch.conflicts
    assert not [op for op in batch.operations if op.issue == 222]


@pytest.mark.parametrize(
    ("record_id", "issue"),
    [("P11-FU-40", 224), ("plan:11.23", 999), ("no-such-record", 222), ("A2A-M17", 225)],
    ids=["no reviewed target", "another issue", "unknown record", "a record that does not migrate"],
)
def test_an_adoption_names_a_migrating_record_and_its_reviewed_target(tmp_path: Path, record_id: str, issue: int) -> None:
    data = _adopt(_good(), record_id, issue, "a" * 64)
    assert any(record_id in problem and "adoption" in problem for problem in _problems(tmp_path, data))


def test_only_the_four_pilots_carry_a_reviewed_adoption() -> None:
    adoptions = json.loads(MANIFEST.read_text(encoding="utf-8"))["adoptions"]
    assert set(adoptions) == set(rules.PILOT_ISSUES) == {"plan:11.23", "P11-FU-20", "P11-FU-40", "A2A-C1"}
    for record_id, adoption in adoptions.items():
        assert adoption["issue"] == rules.PILOT_ISSUES[record_id] and re.fullmatch(r"[0-9a-f]{64}", adoption["fingerprint"])
        assert "pragma: allowlist secret" in adoption["pin"]
    lines = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if '"fingerprint": ' in line]
    assert len(lines) == 4 and all("pragma: allowlist secret" in line for line in lines)  # each digest is pinned on its line


def test_the_status_fact_names_the_status_and_never_cuts_a_sentence() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    short = inventory.baseline_commit[:7]
    drafts = {
        d.record_id: d.body for d in gwt.draft_issues(inventory, gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths))
    }

    def fact(record_id: str) -> str:
        return next(line for line in drafts[record_id].splitlines() if line.startswith("- **Source status at baseline"))

    quoted = "(the leading status of the source quoted below; historical: this issue's state and labels carry the current status)"
    assert fact("P9.87-FU-1") == f"- **Source status at baseline `{short}`:** Open {quoted}"  # its status line soft-wraps
    assert fact("P11.25-FU-1") == f"- **Source status at baseline `{short}`:** Promoted {quoted}"
    assert fact("HARDENING-ITEM-RUFF-LINT-RATCHET").startswith(
        f"- **Source status at baseline `{short}`:** Open (historical: this issue's state and labels carry the current status)."
        " Synthesized: "
    )


# Written after the implementation while planning mutants (a disclosed test-first deviation): branch boundaries.


def test_quote_selectors_match_exactly_their_own_lines() -> None:
    lines = [
        "# Doc",
        "",
        "Prose that mentions **Goal:** mid-line.",
        "**Goal:** the real goal.",
        "",
        "## Section",
        "",
        "```text",
        "## not a heading inside fenced code",
        "```",
        "",
        "### Nested",
        "",
        "Last line of the file.",
        "",
    ]
    assert gwt.quote_span(lines, "line", "**Goal:**") == (4, 4)  # a line that only mentions the text does not match
    assert gwt.quote_span(lines, "section", "Section") == (6, 14)  # through fenced code and nesting, to the end of the file
    with pytest.raises(ValueError, match="matches no"):
        gwt.quote_span(lines, "section", "not a heading inside fenced code")
    assert gwt.quote_span(["~~~", "# fenced", "~~~", "# Real", "text"], "section", "Real") == (4, 5)


def test_a_record_that_does_not_migrate_quotes_no_context(tmp_path: Path) -> None:
    data = _with_source(_good(), POOL)
    data["baseline"]["context"] = {"ctx": {"path": "docs/plans/ctx-plan.md", "blob": gwt.git_blob_id(CONTEXT_DOC.encode("utf-8"))}}
    _records(data)["A2A-M17"]["quotes"] = [["ctx", "line", "**Goal:**"]]
    problems = gwt.validate_inventory(gwt.load_inventory(_write(tmp_path, data)), _read()).problems
    assert any("A2A-M17" in problem and "only a migrating record" in problem for problem in problems), problems


def test_an_adoption_never_bypasses_a_malformed_region(tmp_path: Path) -> None:
    issues = _pilot_issues()
    issues[0]["body"] = "<!-- /optimus-source: PLAN-11.23 -->\n<!-- optimus-source: PLAN-11.23 -->\n"
    data = _adopt(_good(), "plan:11.23", 222, gwt.issue_snapshot(issues[0]).fingerprint)
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    batch = _plan(inventory, drafts, client)
    assert any("plan:11.23" in conflict and "malformed generated region" in conflict for conflict in batch.conflicts)
    assert not [op for op in batch.operations if op.issue == 222]


def test_title_rules_fail_closed() -> None:
    records = [rules._record(id="HARDENING-TRACK-RUFF-LINT", disposition="history")]
    with pytest.raises(ValueError, match="TITLES names records that do not migrate"):
        rules._titles(records, "")
    migrating = [rules._record(id=record_id) for record_id in rules.TITLES] + [rules._record(id="A2A-H99", kind="obligation")]
    with pytest.raises(ValueError, match="no finding heading for A2A-H99"):
        rules._titles(migrating, "### High 4 — Something else\n")


# ==== Task 4: offline governance gates (the plan's named tests over fixtures, the manifest's identities) ====

ISSUES = f"https://github.com/{gwt.REPO}/issues"
HISTORY = f"https://github.com/{gwt.REPO}/blob/{'a' * 40}/docs/superpowers/plans/2026-07-23-consolidated-deferred-followups-backlog.md"
STUB_FIXTURE = f"""\
# Consolidated deferred follow-ups backlog

Current work status lives in [GitHub issues]({ISSUES}) and the [work status page](../../work-status.html).
The pool before the cutover is preserved at [its last commit]({HISTORY}).

## Compatibility anchors

### P11-FU-11: Plan 11.7 retry preflight and live session proof

Tracked in [P11-FU-11]({ISSUES}/301).

### Durable effect-aware MCP indeterminate-call custody

Closed history: [P11-FU-22 at the cutover]({HISTORY}#p11-fu-22-durable-effect-aware-mcp-indeterminate-call-custody).
"""
ANCHORS = {"p11-fu-11-plan-117-retry-preflight-and-live-session-proof", "durable-effect-aware-mcp-indeterminate-call-custody"}
FROZEN_PLAN = "docs/superpowers/plans/plan-11-23.md"
FROZEN_TEXT = b"# Plan 11.23\n\nApproved bytes.\n"


def _identities(data: dict[str, Any], *, finalized: bool = True) -> dict[str, Any]:
    """The fixture with the manifest's identity tables, and (finalized) an issue for every migrating record."""
    data["plan_files"] = {FROZEN_PLAN: {"record": "plan:11.23", "blob": gwt.git_blob_id(FROZEN_TEXT), "pin": "x"}}
    data["plan_exemptions"] = {"docs/superpowers/plans/roadmap.md": "navigation history, no work of its own"}
    data["frozen_artifacts"] = {"docs/a.md": {"sha256": hashlib.sha256(b"frozen").hexdigest(), "pin": "x"}}
    if finalized:
        numbers = iter(range(400, 500))
        for record in data["records"]:
            if record["disposition"] == "migrate" and record.get("target_issue") is None:
                record["target_issue"] = next(numbers)
    return data


def _gated(tmp_path: Path, data: dict[str, Any]) -> gwt.Inventory:
    return gwt.load_inventory(_write(tmp_path, _with_source(data, POOL)))


def _plans(**changes: bytes | None) -> dict[str, bytes]:
    plans = {
        FROZEN_PLAN: FROZEN_TEXT,
        "docs/superpowers/plans/roadmap.md": b"# Roadmap\n",
        "docs/superpowers/plans/new-plan.md": f"# New\n\n**Tracking issue:** {ISSUES}/301\n".encode(),
    }
    for path, data in changes.items():
        key = f"docs/superpowers/plans/{path}.md"
        if data is None:
            plans.pop(key, None)
        else:
            plans[key] = data
    return plans


def test_live_plan_files_have_issue_identity(tmp_path: Path) -> None:
    inventory = _gated(tmp_path, _identities(_good()))
    assert gwt.plan_identity_problems(_plans(), inventory) == []
    cases = {
        "changed since its sealed baseline identity": _plans(**{"plan-11-23": FROZEN_TEXT + b"edited\n"}),
        "no tracking header, no sealed baseline identity": _plans(orphan=b"# Orphan\n"),
        "2 tracking headers": _plans(**{"new-plan": f"**Tracking issue:** {ISSUES}/1\n**Tracking issue:** {ISSUES}/2\n".encode()}),
        "is not an issue of": _plans(**{"new-plan": b"**Tracking issue:** https://github.com/someone/else/issues/3\n"}),
    }
    for expected, plans in cases.items():
        problems = gwt.plan_identity_problems(plans, inventory)
        assert any(expected in problem for problem in problems), (expected, problems)
    data = _identities(_good(), finalized=False)
    data["plan_files"][FROZEN_PLAN]["record"] = "plan:12.1"  # a record whose issue does not exist yet
    problems = gwt.plan_identity_problems(_plans(), _gated(tmp_path, data))
    assert any("plan:12.1" in problem and "no issue identity" in problem for problem in problems), problems


def test_source_mapping_has_no_unclassified_record(tmp_path: Path) -> None:
    assert gwt.mapping_problems(_gated(tmp_path, _identities(_good()))) == []
    problems = gwt.mapping_problems(_gated(tmp_path, _identities(_good(), finalized=False)))
    assert any("P11-FU-40" in problem and "no issue identity" in problem for problem in problems), problems
    data = _identities(_good())
    _records(data)["RISK"]["rationale"] = " "
    _records(data)["A2A-M17"]["rationale"] = ""
    problems = gwt.mapping_problems(_gated(tmp_path, data))
    assert {"RISK", "A2A-M17"} <= {p.split("'")[1] for p in problems if "no reviewed rationale" in p}, problems


def test_source_to_issue_coverage_and_unique_aliases(tmp_path: Path) -> None:
    assert gwt.coverage_problems(_gated(tmp_path, _identities(_good()))) == []
    data = _identities(_good())
    _records(data)["P11-FU-40"]["aliases"] = ["P11-FU-20"]  # another migrating record's identity
    assert any("P11-FU-20" in p and "more than one issue" in p for p in gwt.coverage_problems(_gated(tmp_path, data)))
    data = _identities(_good())
    data["compat_anchors"] = {"p11-fu-40-real-zed-containment": "P11-FU-40", "gone": "P11-FU-404", "registry": "section:x"}
    problems = gwt.coverage_problems(_gated(tmp_path, data))
    assert [p for p in problems if "gone" in p] and not [p for p in problems if "registry" in p or "p11-fu-40" in p], problems


def test_pool_anchors_survive() -> None:
    assert gwt.anchor_problems(STUB_FIXTURE, ANCHORS) == []
    assert any("p11-fu-5-x" in p and "no longer resolves" in p for p in gwt.anchor_problems(STUB_FIXTURE, {*ANCHORS, "p11-fu-5-x"}))
    unlinked = STUB_FIXTURE.replace(f"Tracked in [P11-FU-11]({ISSUES}/301).", "Tracked elsewhere.")
    assert any("points nowhere" in p for p in gwt.anchor_problems(unlinked, ANCHORS))
    twice = STUB_FIXTURE + "\n### Durable effect-aware MCP indeterminate-call custody\n\nAgain.\n"
    assert any("more than one heading" in p for p in gwt.anchor_problems(twice, ANCHORS))
    files = {
        "docs/a.md": f"See [registry](../plans/{gwt.POOL_FILE}#live-implementation-plan-registry) and [top](../plans/{gwt.POOL_FILE}).",
        "tests/b.py": f'LINK = "{gwt.POOL_FILE}#p11-fu-5-windows-subprocess-handle-duplication-flake-winerror-650"',
        "docs/c.md": "Unrelated [link](other.md#a-fragment-of-another-file).",  # not the pool, so not its anchor
    }
    assert gwt.inbound_pool_anchors(files) == {
        "live-implementation-plan-registry",
        "p11-fu-5-windows-subprocess-handle-duplication-flake-winerror-650",
    }


def test_frozen_blobs_unchanged(tmp_path: Path) -> None:
    inventory = _gated(tmp_path, _identities(_good()))
    assert gwt.frozen_problems({"docs/a.md": b"frozen"}.get, inventory) == []
    assert any("changed" in p for p in gwt.frozen_problems({"docs/a.md": b"frozen\r\n"}.get, inventory))
    assert any("missing" in p for p in gwt.frozen_problems({}.get, inventory))
    # Archived with its exact bytes under the repository's archive convention: still the same frozen artifact.
    assert gwt.frozen_problems({"docs/archive/a.md": b"frozen"}.get, inventory) == []
    assert any("changed" in p for p in gwt.frozen_problems({"docs/archive/a.md": b"frozen!"}.get, inventory))


def test_the_real_frozen_artifacts_are_unchanged_at_head() -> None:
    def head(path: str) -> bytes | None:
        try:
            return gwt.git_blob_bytes("HEAD", path)
        except subprocess.CalledProcessError:
            return None

    inventory = gwt.load_inventory(MANIFEST)
    frozen = {record.title for record in inventory.records if record.kind == "frozen-mapping"}
    # The pool states "Pin status: not digest-pinned" for two historical-provenance documents: each may be edited under
    # its own reviewed scope, so the manifest records them but seals no digest for them.
    unpinned = {
        "docs/superpowers/plans/archive/2026-07-23-plan-10-1-p9-96-follow-up-remediation.md",
        "docs/superpowers/specs/2026-08-08-plan-11-9-p11-7-fu-1-gateway-timeout-design.md",
    }
    assert set(inventory.frozen_artifacts) == frozen - unpinned and len(frozen) == 23 and unpinned <= frozen
    assert gwt.frozen_problems(head, inventory) == []


def test_status_stub_has_no_duplicate_board() -> None:
    assert gwt.stub_problems(STUB_FIXTURE) == []
    cases = {
        "table": STUB_FIXTURE + "\n| ID | Status |\n|---|---|\n| P11-FU-1 | Open |\n",
        "status line": STUB_FIXTURE + "\n**Status:** Open.\n",
        "history permalink": STUB_FIXTURE.replace(HISTORY, "https://example.com/pool"),
        "work status page": STUB_FIXTURE.replace("../../work-status.html", "../../elsewhere.html"),
        "GitHub issues": STUB_FIXTURE.replace(f"[GitHub issues]({ISSUES})", "GitHub"),
        "lines": STUB_FIXTURE + "\nfiller\n" * 200,
    }
    for expected, stub in cases.items():
        problems = gwt.stub_problems(stub)
        assert any(expected in problem for problem in problems), (expected, problems)


def test_the_manifest_pins_every_frozen_artifact_digest() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    pool = gwt.git_blob_bytes(data["baseline"]["commit"], rules.SOURCES["pool"]).decode("utf-8")
    bullets = re.findall(r"^- `(docs/superpowers/[^`]+)` — SHA-256 `([0-9A-Fa-f]{64})`(.*)$", pool, re.M)
    stated = {path: digest for path, digest, rest in bullets if "Pin status: not digest-pinned" not in rest}
    assert len(stated) == 21 and len({path for path, _digest, _rest in bullets}) == 23
    assert {path: entry["sha256"] for path, entry in data["frozen_artifacts"].items()} == {p: d.lower() for p, d in stated.items()}
    lines = [line for line in MANIFEST.read_text(encoding="utf-8").splitlines() if '"sha256": ' in line]
    assert len(lines) == len(stated) and all("pragma: allowlist secret" in line for line in lines)


def test_the_manifest_gives_every_docs_root_plan_one_identity() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    commit = data["baseline"]["commit"]
    plans = gwt.read_plans_at(commit)
    assert set(data["plan_files"]) | set(data["plan_exemptions"]) == set(plans)
    assert not set(data["plan_files"]) & set(data["plan_exemptions"])
    records = {r["id"]: r for r in data["records"]}
    for path, entry in data["plan_files"].items():
        assert entry["blob"] == gwt.git_blob_id(plans[path]) and records[entry["record"]]["disposition"] == "migrate", path
        assert "pragma: allowlist secret" in entry["pin"]
    owners = {path.rsplit("/", 1)[1]: entry["record"] for path, entry in data["plan_files"].items()}
    assert owners["2026-08-18-plan-11-23-p11-fu-20-client-mcp-runtime-composition.md"] == "plan:11.23"
    assert owners["2026-07-29-plan-11-7-p11-feat-zed-resume-implementation_v3.md"] == "plan:11.7"
    assert owners["hardening-runtime-quality-masterplan.md"] == "HARDENING-FEAT-RUNTIME-QUALITY"
    assert owners["hardening-ci-guardrail-truthfulness-implementation.md"] == "HARDENING-TRACK-CI-GUARDRAILS"
    assert all(rationale.strip() for rationale in data["plan_exemptions"].values())
    assert set(data["plan_exemptions"]) == {f"{gwt.PLANS_DIR}{name}" for name in rules.PLAN_EXEMPTIONS}


def test_finalize_records_each_migrating_record_issue_once(tmp_path: Path) -> None:
    data = _identities(_good(), finalized=False)
    migrating = [r["id"] for r in data["records"] if r["disposition"] == "migrate"]
    mapping = {record_id: 500 + index for index, record_id in enumerate(migrating) if record_id not in ("plan:11.23", "P11-FU-20")}
    mapping |= {"plan:11.23": 222, "P11-FU-20": 223}
    final = gwt.finalize_inventory(data, mapping)
    assert {r["id"]: r["target_issue"] for r in final["records"] if r["disposition"] == "migrate"} == mapping
    assert "target_issue" not in _records(data)["P11-FU-40"]  # the input is left untouched
    for broken, expected in [
        ({k: v for k, v in mapping.items() if k != "P11-FU-40"}, "P11-FU-40"),
        ({**mapping, "nobody": 9}, "nobody"),
        ({**mapping, "plan:11.23": 999}, "plan:11.23"),
        ({**mapping, "P11-FU-40": mapping["plan:12.1"]}, "more than one record"),
        ({**mapping, "P11-FU-40": 0}, "P11-FU-40"),
    ]:
        with pytest.raises(ValueError, match=re.escape(expected)):
            gwt.finalize_inventory(data, broken)


# Written after the gates' implementation while planning mutants (a disclosed test-first deviation): branch boundaries.


def test_gate_branches_fail_closed(tmp_path: Path) -> None:
    data = _identities(_good())
    data["plan_files"][FROZEN_PLAN]["record"] = "no-such-record"
    problems = gwt.plan_identity_problems(_plans(), _gated(tmp_path, data))
    assert any("no-such-record" in problem and "no issue identity" in problem for problem in problems), problems

    data = _identities(_good())
    _records(data)["A2A-M17"].update(rationale=" ", terminal_disposition="closed through the archived closure plan")
    assert gwt.mapping_problems(_gated(tmp_path, data)) == []  # a terminal disposition is a reviewed rationale
    _records(data)["A2A-M17"].update(disposition="duplicate", duplicate_of="A2A-C1")
    assert gwt.mapping_problems(_gated(tmp_path, data)) == []
    _records(data)["A2A-M17"]["duplicate_of"] = "RISK"  # not a migrating record
    assert any("A2A-M17" in problem and "duplicate of 'RISK'" in problem for problem in gwt.mapping_problems(_gated(tmp_path, data)))

    assert any("status line" in problem for problem in gwt.stub_problems(STUB_FIXTURE + "\n- Current status: Open\n"))

    final_data = _identities(_good(), finalized=False)
    complete = {r["id"]: r.get("target_issue") or 600 + i for i, r in enumerate(final_data["records"]) if r["disposition"] == "migrate"}
    for bad in (True, "301", 2.0):
        with pytest.raises(ValueError, match="not a positive issue number"):
            gwt.finalize_inventory(final_data, {**complete, "P11-FU-40": bad})


def test_plan_identity_rules_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    commit = json.loads(MANIFEST.read_text(encoding="utf-8"))["baseline"]["commit"]
    sources, plans = gwt.read_sources_at(commit, rules.READS), gwt.read_plans_at(commit)
    monkeypatch.setattr(rules, "PLAN_EXEMPTIONS", {**rules.PLAN_EXEMPTIONS, "gone.md": "no longer here"})
    with pytest.raises(ValueError, match="gone.md"):
        rules.draft_inventory(commit, sources, plans)
    monkeypatch.undo()
    orphan = {**plans, gwt.PLANS_DIR + "2026-12-01-orphan.md": b"# An unowned plan\n"}
    with pytest.raises(ValueError, match="orphan.md has owners \\[\\]"):
        rules.draft_inventory(commit, sources, orphan)
    path = "docs/superpowers/plans/archive/x.md"
    twice = f"- `{path}` — SHA-256 `{'A' * 64}` — one\n- `{path}` — SHA-256 `{'B' * 64}` — two\n"
    with pytest.raises(ValueError, match="two digests"):
        rules._frozen_artifacts(twice)
    once = rules._frozen_artifacts(f"- `{path}` — SHA-256 `{'A' * 64}` — one\n- `{path}` — SHA-256 `{'a' * 64}` — again\n")
    assert once == {path: {"sha256": "a" * 64, "pin": rules.DIGEST_PIN_NOTE}}  # one artifact, stated twice, same digest


def test_only_digest_pinned_frozen_bullets_are_sealed() -> None:
    pinned, unpinned = "docs/superpowers/plans/archive/p.md", "docs/superpowers/specs/u.md"
    pool = (
        f"- `{pinned}` — SHA-256 `{'A' * 64}` — Frozen approval bytes.\n"
        f"- `{unpinned}` — SHA-256 `{'B' * 64}` — Historical provenance. Pin status: not digest-pinned. Editable.\n"
        f"- `{pinned}` — SHA-256 `{'A' * 64}` — Pin status: not digest-pinned here, but frozen above.\n"
    )
    assert rules._frozen_artifacts(pool) == {pinned: {"sha256": "a" * 64, "pin": rules.DIGEST_PIN_NOTE}}


# ==== Task 4: the cutover change set (the pool stub and issue placeholders, rendered from a finalized manifest) ====

CUTOVER = "c" * 40
COMPAT = {
    "live-implementation-plan-registry": "section:live-implementation-plan-registry",
    "p11-fu-40-real-zed-containment": "P11-FU-40",
    "p11-fu-40-a-broken-older-fragment": "P11-FU-40",
    "plan-117-accepted-risk-redis-durability": "RISK",
}
HEADINGS = {"p11-fu-40-a-broken-older-fragment": "P11-FU-40: A broken older fragment"}


def _cutover_inventory(tmp_path: Path, compat: dict[str, str] = COMPAT) -> gwt.Inventory:
    data = _identities(_good())
    data["compat_anchors"] = compat
    return _gated(tmp_path, data)


def test_the_pool_stub_keeps_every_anchor_and_no_board(tmp_path: Path) -> None:
    inventory = _cutover_inventory(tmp_path)
    stub = gwt.render_pool_stub(inventory, POOL, CUTOVER, set(COMPAT), HEADINGS)
    assert gwt.stub_problems(stub) == [] and gwt.anchor_problems(stub, set(COMPAT)) == []
    history = f"https://github.com/{gwt.REPO}/blob/{CUTOVER}/{gwt.POOL_PATH}"
    fu40 = {r.id: r.target_issue for r in inventory.records}["P11-FU-40"]
    assert f"({ISSUES}/{fu40})" in stub and f"({history}#p11-fu-40-real-zed-containment)" in stub
    assert "### P11-FU-40: Real Zed containment" in stub  # the pool's own heading reproduces its anchor
    assert "### P11-FU-40: A broken older fragment" in stub  # a reviewed heading reproduces a fragment no heading had
    assert stub.count(f"({history}#p11-fu-40-real-zed-containment)") == 2  # ...and links its record's own entry
    assert f"({history}#live-implementation-plan-registry)" in stub and "label%3Akind%3Aplan" in stub
    assert f"({history}#plan-117-accepted-risk-redis-durability)" in stub and "not open work" in stub
    assert "Partially implemented" not in stub and "| `P11-FU-20`" not in stub  # no status and no board survive


@pytest.mark.parametrize(
    ("anchors", "headings", "expected"),
    [
        ({"p11-fu-40-a-broken-older-fragment"}, {}, "no heading"),
        ({"p11-fu-40-a-broken-older-fragment"}, {"p11-fu-40-a-broken-older-fragment": "Another title"}, "does not reproduce"),
        ({"an-inbound-anchor-nobody-reviewed"}, {}, "no reviewed target"),
    ],
)
def test_the_pool_stub_refuses_an_anchor_it_cannot_reproduce(
    tmp_path: Path, anchors: set[str], headings: dict[str, str], expected: str
) -> None:
    with pytest.raises(ValueError, match=expected):
        gwt.render_pool_stub(_cutover_inventory(tmp_path), POOL, CUTOVER, anchors, headings)


def test_the_pool_stub_replaces_only_the_inventoried_pool(tmp_path: Path) -> None:
    edited = POOL + "\n### P11-FU-99: Filed after the baseline\n\nAn item the manifest never saw.\n"
    with pytest.raises(ValueError, match="not the pool the manifest inventoried"):
        gwt.render_pool_stub(_cutover_inventory(tmp_path), edited, CUTOVER, set(COMPAT), HEADINGS)
    with pytest.raises(ValueError, match="history permalink"):
        gwt.render_pool_stub(_cutover_inventory(tmp_path), POOL, "main", set(COMPAT), HEADINGS)  # a moving ref


def test_the_pool_stub_needs_a_finalized_manifest(tmp_path: Path) -> None:
    data = _identities(_good(), finalized=False)
    data["compat_anchors"] = COMPAT
    with pytest.raises(ValueError, match="P11-FU-40.*no issue"):
        gwt.render_pool_stub(_gated(tmp_path, data), POOL, CUTOVER, set(COMPAT), HEADINGS)


def test_issue_placeholders_are_filled_only_from_a_finalized_manifest(tmp_path: Path) -> None:
    inventory = _cutover_inventory(tmp_path)
    fu40 = {r.id: r.target_issue for r in inventory.records}["P11-FU-40"]
    text = "**Tracking issue:** {{issue:P11-FU-40}}\nSee {{issue:plan:11.23}}.\n"
    assert gwt.fill_issue_placeholders(text, inventory) == f"**Tracking issue:** {ISSUES}/{fu40}\nSee {ISSUES}/222.\n"
    with pytest.raises(ValueError, match="nobody"):
        gwt.fill_issue_placeholders("{{issue:nobody}}", inventory)
    with pytest.raises(ValueError, match="A2A-M17"):
        gwt.fill_issue_placeholders("{{issue:A2A-M17}}", inventory)  # it does not migrate, so it has no issue
    with pytest.raises(ValueError, match="malformed"):
        gwt.fill_issue_placeholders("{{issue: P11-FU-40}}", inventory)  # never left behind unfilled
    unfinalized = _gated(tmp_path, _identities(_good(), finalized=False))
    with pytest.raises(ValueError, match="P11-FU-40"):
        gwt.fill_issue_placeholders("{{issue:P11-FU-40}}", unfinalized)
    assert gwt.fill_issue_placeholders("no placeholders here", unfinalized) == "no placeholders here"


def _git_add(root: Path) -> None:
    """Stage everything under ``root`` in a fresh repository: the cutover scans the Git index, not the filesystem."""
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)


def test_cli_cutover_docs_writes_the_stub_and_fills_the_placeholders(tmp_path: Path) -> None:
    compat = {anchor: target for anchor, target in COMPAT.items() if anchor not in HEADINGS}
    data = _identities(_good())
    data["compat_anchors"] = compat
    inventory_path = _write(tmp_path, _with_source(data, POOL))
    root = tmp_path / "checkout"
    (root / gwt.PLANS_DIR).mkdir(parents=True)
    (root / gwt.POOL_PATH).write_text(POOL, encoding="utf-8")
    note = root / "docs/note.md"
    note.write_text(
        f"Owner: {{{{issue:P11-FU-40}}}}; [entry](superpowers/plans/{gwt.POOL_FILE}#p11-fu-40-real-zed-containment)\n", encoding="utf-8"
    )
    reader = lambda commit, paths: {name: POOL.encode("utf-8") for name in paths}  # noqa: E731 - the pool at the cutover commit
    argv = ["cutover-docs", str(inventory_path), "--history-commit", CUTOVER, "--root", str(root)]
    assert gwt.main(argv, reader=reader) == 2  # not a Git checkout: there is no index to scan, so nothing is written
    stray = root / "docs/stray.md"
    stray.write_text(f"[old](superpowers/plans/{gwt.POOL_FILE}#an-unreviewed-fragment)\n", encoding="utf-8")
    _git_add(root)
    assert gwt.main(argv, reader=reader) == 2  # an inbound anchor nobody reviewed: nothing is written
    assert (root / gwt.POOL_PATH).read_text(encoding="utf-8") == POOL and "{{issue:P11-FU-40}}" in note.read_text(encoding="utf-8")
    stray.unlink()
    _git_add(root)
    assert gwt.main(argv, reader=reader) == 0
    inventory = gwt.load_inventory(inventory_path)
    stub = gwt.render_pool_stub(inventory, POOL, CUTOVER, set(compat), rules.COMPAT_HEADINGS)
    assert (root / gwt.POOL_PATH).read_text(encoding="utf-8") == stub
    fu40 = {r.id: r.target_issue for r in inventory.records}["P11-FU-40"]
    assert note.read_text(encoding="utf-8").startswith(f"Owner: {ISSUES}/{fu40};")
    assert gwt.main(argv, reader=reader) == 2  # the root's pool is now the stub, not the pool at the history commit
    assert (root / gwt.POOL_PATH).read_text(encoding="utf-8") == stub


def test_the_reviewed_compat_headings_reproduce_exactly_the_broken_anchors() -> None:
    commit = json.loads(MANIFEST.read_text(encoding="utf-8"))["baseline"]["commit"]
    pool = gwt.git_blob_bytes(commit, rules.SOURCES["pool"]).decode("utf-8")
    slugs = {gwt.heading_anchor(title) for _number, _level, title in gwt._headings(pool.splitlines())}
    assert set(rules.COMPAT_ANCHORS) - slugs == set(rules.COMPAT_HEADINGS)  # only anchors no pool heading reproduces
    assert all(gwt.heading_anchor(heading) == anchor for anchor, heading in rules.COMPAT_HEADINGS.items())


def test_cli_finalize_writes_the_manifest_with_every_issue(tmp_path: Path) -> None:
    data = _identities(_good(), finalized=False)
    inventory_path = _write(tmp_path, _with_source(data, POOL))
    numbers = iter(range(700, 800))
    mapping = {r["id"]: r.get("target_issue") or next(numbers) for r in data["records"] if r["disposition"] == "migrate"}
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    out = tmp_path / "final.json"
    assert gwt.main(["finalize", str(inventory_path), "--mapping", str(mapping_path), "--out", str(out)]) == 0
    assert (
        out.read_bytes()
        == gwt.render_manifest(gwt.finalize_inventory(json.loads(inventory_path.read_text(encoding="utf-8")), mapping)).encode()
    )
    mapping_path.write_text(json.dumps({**mapping, "P11-FU-40": 0}), encoding="utf-8")
    assert gwt.main(["finalize", str(inventory_path), "--mapping", str(mapping_path), "--out", str(tmp_path / "bad.json")]) == 2
    assert not (tmp_path / "bad.json").exists()


def test_cli_reconcile_writes_its_mapping_only_when_it_reconciles(tmp_path: Path) -> None:
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    _publish_cli(tmp_path, client, "run", "--pause-seconds", "0", "--execute")  # plans, then publishes the fixture batch
    path = tmp_path / "inventory.json"
    reader = lambda commit, paths: {"pool": POOL.encode("utf-8")}  # noqa: E731 - fixture reader
    out = tmp_path / "mapping.json"
    assert gwt.main(["reconcile", str(path), "--mapping-out", str(out)], reader=reader, client=client) == 0
    mapping = json.loads(out.read_text(encoding="utf-8"))
    assert mapping["plan:11.23"] == 222 and mapping["P11-FU-20"] == 223 and len(mapping) == 8
    client.issues[222]["body"] = "edited"
    out.unlink(missing_ok=True)
    assert gwt.main(["reconcile", str(path), "--mapping-out", str(out)], reader=reader, client=client) == 1
    assert not out.exists()


# Written after the generator's implementation while planning mutants (a disclosed test-first deviation): branches.


def test_the_pool_stub_links_every_kind_of_target(tmp_path: Path) -> None:
    data = _identities(_good())
    _records(data)["A2A-M17"].update(disposition="duplicate", duplicate_of="A2A-C1")
    compat = {"a2a-ledger-audit-obligations": "A2A-M17", "a2a-c1-an-older-fragment": "A2A-C1"}
    data["compat_anchors"] = compat
    inventory = _gated(tmp_path, data)
    c1 = _records(data)["A2A-C1"]["target_issue"]
    history = f"https://github.com/{gwt.REPO}/blob/{CUTOVER}/{gwt.POOL_PATH}"
    stub = gwt.render_pool_stub(inventory, POOL, CUTOVER, set(compat), {"a2a-c1-an-older-fragment": "A2A C1: an older fragment"})
    # A duplicate links its original's issue; a pool heading links itself even when its record is only a table row.
    assert (
        f"A duplicate of A2A-C1, tracked in [A2A-C1]({ISSUES}/{c1}); history: [its entry at the cutover]({history}#a2a-ledger-audit-obligations)."
        in stub
    )
    # A reviewed heading for a record without a heading of its own links the whole pool at the cutover.
    assert f"Tracked in [A2A-C1]({ISSUES}/{c1}); history: [the pool at the cutover]({history})." in stub
    data["compat_anchors"] = {"gone": "P11-FU-404"}
    with pytest.raises(ValueError, match="points to unknown record 'P11-FU-404'"):
        gwt.render_pool_stub(_gated(tmp_path, data), POOL, CUTOVER, {"gone"}, {"gone": "Gone"})
    data["compat_anchors"] = {"pool": "P11-FU-40"}  # the pool's own title: the stub would carry that heading twice
    with pytest.raises(ValueError, match="more than one heading"):
        gwt.render_pool_stub(_gated(tmp_path, data), POOL, CUTOVER, {"pool"}, {})


def test_cutover_docs_scans_every_tracked_file_and_fills_only_markdown(tmp_path: Path) -> None:
    data = _identities(_good())
    data["compat_anchors"] = {"p11-fu-40-real-zed-containment": "P11-FU-40"}
    inventory = _gated(tmp_path, data)
    root = tmp_path / "checkout"
    for path, content in {
        gwt.POOL_PATH: POOL,
        "tests/fixture.py": 'TEXT = "{{issue:P11-FU-40}}"\n',  # code is never filled
        ".github/workflows/x.yml": f"# {gwt.POOL_FILE}#p11-fu-40-real-zed-containment\n",  # any tracked file type links
    }.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content, encoding="utf-8")
    _git_add(root)
    # Repository truth is the Git index (tools/tracked_repository_files.py): an untracked or ignored file is not scanned.
    (root / "docs/unstaged-draft.md").write_text(f"[old]({gwt.POOL_FILE}#an-unreviewed-fragment)\n", encoding="utf-8")
    changed = gwt.cutover_docs(inventory, root, POOL.encode("utf-8"), CUTOVER, {})
    assert set(changed) == {gwt.POOL_PATH}
    (root / ".github/workflows/x.yml").write_text(f"# {gwt.POOL_FILE}#an-unreviewed-fragment\n", encoding="utf-8")
    with pytest.raises(ValueError, match="an-unreviewed-fragment"):
        gwt.cutover_docs(inventory, root, POOL.encode("utf-8"), CUTOVER, {})
    _records(data)["A2A-M17"]["target_issue"] = 999  # a retiring record never lends its number
    with pytest.raises(ValueError, match="'A2A-M17' does not migrate"):
        gwt.fill_issue_placeholders("{{issue:A2A-M17}}", _gated(tmp_path, data))


@pytest.mark.parametrize("malformed", ["a list of every migrating record", "not JSON"])
def test_cli_finalize_refuses_a_malformed_mapping(tmp_path: Path, malformed: str) -> None:
    data = _identities(_good(), finalized=False)
    inventory_path = _write(tmp_path, _with_source(data, POOL))
    migrating = [r["id"] for r in data["records"] if r["disposition"] == "migrate"]
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps(migrating) if malformed.startswith("a list") else "{not json", encoding="utf-8")
    assert gwt.main(["finalize", str(inventory_path), "--mapping", str(mapping_path), "--out", str(tmp_path / "out.json")]) == 2
    assert not (tmp_path / "out.json").exists()


# ==== Task 4: batched publication (2026-10-05 ruling, Option A): a record selection over the full inventory ====


def _selection(tmp_path: Path, name: str, *record_ids: str) -> Path:
    path = tmp_path / f"{name}.txt"
    path.write_text("".join(f"{record_id}\n" for record_id in record_ids), encoding="utf-8")
    return path


def _ops(batch: gwt.MigrationBatch) -> list[tuple[str, str, str]]:
    return [(operation.op, operation.target, operation.payload_sha256) for operation in batch.operations]


BATCHES = (
    ("plan:11.23", "P11-FU-20"),  # the pilot updates
    ("P11.25-FU-1", "A2A-C1"),  # a child before its parent: its binding waits for the parent's batch
    ("plan:12.1", "P12-FU-1", "P11-FU-40", "H4"),
)


def _publish_batches(tmp_path: Path, inventory: gwt.Inventory, drafts: list[gwt.IssueDraft], client: FakeGitHub, count: int) -> None:
    for number, records in enumerate(BATCHES[:count]):
        batch = gwt.plan_migration(inventory, drafts, gwt.read_issues(client), gwt.read_labels(client), frozenset(records))
        assert batch.conflicts == ()
        assert _publish(tmp_path, batch, client, name=f"batch-{number}.jsonl")[0].outcome == "pass"


def test_selected_batches_apply_exactly_the_full_plan(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    full = _ops(_plan(inventory, drafts, client))
    applied: list[tuple[str, str, str]] = []
    done: set[str] = set()
    for number, records in enumerate(BATCHES):
        selected = frozenset(records)
        batch = gwt.plan_migration(inventory, drafts, gwt.read_issues(client), gwt.read_labels(client), selected)
        assert batch.conflicts == ()
        for operation in batch.operations:  # a batch writes only for its own records
            if operation.op == "create-label":
                assert any(operation.target in draft.labels for draft in drafts if draft.record_id in selected)
            elif operation.op == "bind-sub-issue":
                assert {operation.payload["child"], operation.payload["parent"]} & selected
            else:
                assert operation.target in selected
        result, _journal = _publish(tmp_path, batch, client, name=f"batch-{number}.jsonl")
        assert result.outcome == "pass"
        applied += _ops(batch)
        done |= selected
        assert gwt.reconcile(inventory, drafts, gwt.read_issues(client), frozenset(done)).problems == ()

        again = gwt.plan_migration(inventory, drafts, gwt.read_issues(client), gwt.read_labels(client), selected)
        if number == 0:  # the adopted pilots now equal their drafts
            assert again.operations == () and again.conflicts == ()
            continue
        assert any("no reviewed target issue" in conflict for conflict in again.conflicts)  # recovery is never a re-run
        writes = len(client.writes)
        assert _publish(tmp_path, again, client, name=f"rerun-{number}.jsonl")[0].outcome == "refused"
        assert len(client.writes) == writes

    assert [op for op in applied if op[0] == "bind-sub-issue"][0][1] == "P11.25-FU-1 <- plan:12.1"  # bound in the parent's batch
    assert sorted(applied) == sorted(full)  # the batches partition the whole plan: nothing lost, nothing twice
    report = gwt.reconcile(inventory, drafts, gwt.read_issues(client))
    assert report.ok and len(report.mapping) == 8


def test_a_selected_reconcile_checks_every_existing_issue_across_the_repository(tmp_path: Path) -> None:
    inventory, drafts, client = _setup(tmp_path)
    _publish_batches(tmp_path, inventory, drafts, client, 2)
    selected = frozenset(BATCHES[1])
    report = gwt.reconcile(inventory, drafts, gwt.read_issues(client), selected)
    assert report.problems == ()
    numbers = report.mapping
    full = gwt.reconcile(inventory, drafts, gwt.read_issues(client)).problems
    assert sorted(problem.split("'")[1] for problem in full) == sorted(BATCHES[2])  # only the unpublished batch is missing
    assert all("has no issue carrying its source marker" in problem for problem in full)

    def broken(change: Any) -> list[str]:
        issues = copy.deepcopy(client.issues)
        change(issues)
        return list(gwt.reconcile(inventory, drafts, gwt.read_issues(FakeGitHub(list(issues.values()))), selected).problems)

    cases = {  # outside the selection: a duplicate, a foreign marker and an edited earlier issue are still found
        "'P11-FU-20' source marker is on more than one issue": lambda issues: issues.update(
            {900: _issue(900, body="<!-- optimus-source: P11-FU-20 -->")}
        ),
        "no migrating record owns": lambda issues: issues.update({901: _issue(901, body="<!-- optimus-source: P11-FU-999 -->")}),
        "'plan:11.23': #222 body's generated region differs": lambda issues: issues[222].update(
            body=issues[222]["body"].replace("<!-- /optimus-source: PLAN-11.23 -->", "edited\n<!-- /optimus-source: PLAN-11.23 -->")
        ),
        "'P12-FU-1' source marker is on more than one issue": lambda issues: issues.update(
            {902: _issue(902, body="<!-- optimus-source: P12-FU-1 -->"), 903: _issue(903, body="<!-- optimus-source: P12-FU-1 -->")}
        ),
        "'A2A-C1' has no issue carrying its source marker": lambda issues: issues.pop(numbers["A2A-C1"]),
    }
    for expected, change in cases.items():
        problems = broken(change)
        assert any(expected in problem for problem in problems), (expected, problems)


def test_cli_only_selects_records_and_refuses_a_bad_selection(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(tmp_path, _with_source(_good(), POOL))
    reader = lambda commit, paths: {"pool": POOL.encode("utf-8")}  # noqa: E731 - fixture reader
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    only = ["--only", str(_selection(tmp_path, "pilots", *BATCHES[0])), "--only", str(_selection(tmp_path, "second", *BATCHES[1]))]
    batch_path = tmp_path / "batch.json"

    assert gwt.main(["plan", str(path), "--out", str(batch_path), *only], reader=reader, client=client) == 0
    operations = json.loads(batch_path.read_text(encoding="utf-8"))["operations"]
    assert {op["target"] for op in operations if op["op"] in ("create-issue", "update-issue")} == {*BATCHES[0], *BATCHES[1]}
    publish = ["publish", str(path), "--batch", str(batch_path), "--pause-seconds", "0", "--execute"]
    assert gwt.main([*publish, "--evidence-dir", str(tmp_path / "whole")], reader=reader, client=client) == 2
    assert client.writes == []  # without the reviewed selection, a fresh plan is another batch
    assert gwt.main([*publish, "--evidence-dir", str(tmp_path / "run"), *only], reader=reader, client=client) == 0
    assert len(client.writes) == len(operations)
    assert gwt.main(["reconcile", str(path), *only], reader=reader, client=client) == 0
    assert gwt.main(["reconcile", str(path)], reader=reader, client=client) == 1  # the full inventory is not yet published
    capsys.readouterr()

    reads = len(client.log)
    refusals = {
        "unknown": (("P11-FU-999",), "'P11-FU-999'"),
        "history": (("A2A-M17",), "'A2A-M17'"),
        "twice": (("H4", "H4"), "more than once"),
        "empty": ((), "names no record"),
    }
    for name, (records, expected) in refusals.items():
        bad = _selection(tmp_path, name, *records)
        assert gwt.main(["plan", str(path), "--out", str(tmp_path / f"{name}.json"), "--only", str(bad)], reader=reader, client=client) == 2
        assert expected in json.loads(capsys.readouterr().out)["reason"] and not (tmp_path / f"{name}.json").exists()
    overlap = ["reconcile", str(path), *only, "--only", str(_selection(tmp_path, "overlap", "A2A-C1"))]
    assert gwt.main(overlap, reader=reader, client=client) == 2
    assert "more than once" in json.loads(capsys.readouterr().out)["reason"]
    missing = ["plan", str(path), "--out", str(tmp_path / "missing.json"), "--only", str(tmp_path / "absent.txt")]
    assert gwt.main(missing, reader=reader, client=client) == 2
    mapping = ["reconcile", str(path), *only, "--mapping-out", str(tmp_path / "mapping.json")]
    assert gwt.main(mapping, reader=reader, client=client) == 2
    assert "full reconcile" in json.loads(capsys.readouterr().out.splitlines()[-1])["reason"]
    assert not (tmp_path / "mapping.json").exists()
    assert len(client.log) == reads  # every refusal comes before any GitHub read


# ==== Checkpoint 3 review fixes (Fable 5.1, 2026-10-05): kept pilot text, sealed identities, visible headers ====


def _retaining_pilot() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A legacy pilot adopted at its reviewed fingerprint, retaining two reviewed paragraphs of its body as one passage."""
    issues = _legacy_pilot_issues()
    issues[0]["body"] += "\nCustody: reviewed pilot custody text.\n"
    data = _adopt(_good(), "plan:11.23", 222, gwt.issue_snapshot(issues[0]).fingerprint)
    _records(data)["plan:11.23"]["retained"] = ["Codex-drafted pilot body\n\nCustody: reviewed pilot custody text."]
    return data, issues


def test_an_adopted_pilot_keeps_its_reviewed_passages_quoted_in_the_region(tmp_path: Path) -> None:
    data, issues = _retaining_pilot()
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    region = {draft.record_id: draft.body for draft in drafts}["plan:11.23"]
    assert "> Codex-drafted pilot body\n>\n> Custody: reviewed pilot custody text.\n" in region  # quoted exactly
    assert region.index("## Reviewed pilot passages") < region.index("## Source at baseline")
    batch = _plan(inventory, drafts, client)
    assert batch.conflicts == ()
    update = next(op for op in batch.operations if op.issue == 222)
    assert update.payload["body"] == region.rstrip("\n")  # the passages live inside the generated region
    result, _journal = _publish(tmp_path, batch, client)
    assert result.outcome == "pass"
    assert gwt.reconcile(inventory, drafts, gwt.read_issues(client)).problems == ()
    without = {draft.record_id: draft.body for draft in drafts}["P11-FU-20"]
    assert "## Reviewed pilot passages" not in without  # only a record that retains passages has the section


def test_a_retained_passage_the_live_body_lacks_is_a_conflict(tmp_path: Path) -> None:
    data, issues = _retaining_pilot()
    _records(data)["plan:11.23"]["retained"] = ["Codex-drafted pilot body", "Custody: text nobody reviewed."]
    inventory, drafts, client = _setup(tmp_path, data, issues=issues)
    batch = _plan(inventory, drafts, client)
    assert any("plan:11.23" in c and "reviewed pilot passage 2" in c for c in batch.conflicts), batch.conflicts
    assert not [op for op in batch.operations if op.issue == 222]


@pytest.mark.parametrize(
    ("retained", "adopted", "expected"),
    [
        (["kept"], False, "only a record with a reviewed adoption"),
        ([" \n "], True, "empty"),
        ([" padded"], True, "surrounding whitespace"),
        (["<!-- /optimus-source: PLAN-11.23 -->"], True, "source marker"),
        (["kept", "kept"], True, "more than once"),
    ],
    ids=["no adoption", "empty", "padded", "a source marker", "repeated"],
)
def test_retained_pilot_passages_fail_closed(tmp_path: Path, retained: list[str], adopted: bool, expected: str) -> None:
    data = _adopt(_good(), "plan:11.23", 222, "a" * 64) if adopted else _good()
    _records(data)["plan:11.23"]["retained"] = retained
    problems = _problems(tmp_path, data)
    assert any("plan:11.23" in problem and expected in problem for problem in problems), problems


def test_the_real_pilots_retain_every_reviewed_paragraph_their_sources_do_not_carry() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    sources = gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths)
    drafts = {draft.record_id: draft.body for draft in gwt.draft_issues(inventory, sources)}
    retained = {record.id: record.retained for record in inventory.records if record.retained}
    assert set(retained) == set(inventory.adoptions) == set(rules.PILOT_RETAINED)
    for record_id, passages in retained.items():
        for passage in passages:
            assert gwt.quote_block(passage) in drafts[record_id], record_id
            assert "Trial copy for the tracking pilot" not in passage and "optimus-source" not in passage
    text = {record_id: "\n".join(passages) for record_id, passages in retained.items()}
    assert "Closing FU20 alone is not automatic plan acceptance." in text["plan:11.23"]  # the closure rule
    assert "owns the unsatisfied live prerequisite gate" in text["plan:11.23"]  # the Task 6 gate pointer
    assert "Historical suggested ownership is not new implementation authority" in text["P11-FU-20"]
    assert "## Acceptance design boundary" in text["A2A-C1"] and "historical audit evidence" in text["A2A-C1"]
    assert "Custody: P11.26-CAND-1-RESOURCE-LIFETIME." in text["P11-FU-40"]


def test_a_sealed_plan_keeps_its_sealed_identity_when_it_gains_a_header(tmp_path: Path) -> None:
    inventory = _gated(tmp_path, _identities(_good()))
    rebound = FROZEN_TEXT + f"\n**Tracking issue:** {ISSUES}/999\n".encode()
    problems = gwt.plan_identity_problems(_plans(**{"plan-11-23": rebound}), inventory)
    assert any(FROZEN_PLAN in p and "#999" in p and "#222" in p for p in problems), problems
    kept = FROZEN_TEXT + f"\n**Tracking issue:** {ISSUES}/222\n".encode()  # a changed sealed plan naming its own issue
    assert gwt.plan_identity_problems(_plans(**{"plan-11-23": kept}), inventory) == []


def test_tracking_headers_count_only_where_a_reader_sees_them() -> None:
    header = f"**Tracking issue:** {ISSUES}/301"
    assert gwt.tracking_issue(f"# Plan\n\n```markdown\n{header}\n```\n", "p.md") is None
    assert gwt.tracking_issue(f"# Plan\n\n<!--\n{header}\n-->\n", "p.md") is None
    assert gwt.tracking_issue(f"# Plan\n\n<!-- draft, never closed\n{header}\n", "p.md") is None
    visible = f"# Plan\n\n**Tracking issue:** {ISSUES}/302\n\n~~~\n{header}\n~~~\n\nText <!-- aside --> after.\n"
    assert gwt.tracking_issue(visible, "p.md") == 302  # a fenced example is not a second header


def test_an_uppercase_inbound_anchor_names_its_lowercase_form() -> None:
    upper = "Durable-Effect-Aware-MCP-Indeterminate-Call-Custody"
    problems = gwt.anchor_problems(STUB_FIXTURE, {upper})
    assert len(problems) == 1 and "uppercase" in problems[0] and upper.lower() in problems[0], problems


@pytest.mark.parametrize(
    "placeholder", ["{{ issue:P11-FU-40 }}", "{{Issue:P11-FU-40}}", "{{ISSUE: P11-FU-40}}", "{{issue:P11-FU-40}}x", "{{issue:P11-FU-40}}_"]
)
def test_a_malformed_or_glued_issue_placeholder_is_refused(tmp_path: Path, placeholder: str) -> None:
    inventory = _cutover_inventory(tmp_path)
    with pytest.raises(ValueError, match="malformed"):
        gwt.fill_issue_placeholders(f"See {placeholder}.", inventory)
    root = tmp_path / "checkout"
    for path, content in {gwt.POOL_PATH: POOL, "docs/note.md": f"Owner: {placeholder}\n"}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content, encoding="utf-8")
    _git_add(root)
    with pytest.raises(ValueError, match="malformed"):  # the cutover never leaves such a document unfilled
        gwt.cutover_docs(inventory, root, POOL.encode("utf-8"), CUTOVER, {})


# Found by the preview's full suite after merging the fixes above: the kept pilot passages link the pool at commit
# 980dad0, and such a commit-pinned permalink was counted as a link the stub must keep.


def test_a_commit_pinned_permalink_is_not_an_inbound_pool_link() -> None:
    plans = f"https://github.com/{gwt.REPO}/blob"
    files = {
        "tools/rules.py": f'TEXT = "[old]({plans}/{"a" * 40}/docs/superpowers/plans/{gwt.POOL_FILE}#pinned-anchor)"',
        "docs/a.md": f"[live]({plans}/main/docs/superpowers/plans/{gwt.POOL_FILE}#branch-anchor) and [rel](plans/{gwt.POOL_FILE}#rel-anchor)",
    }
    # A pinned permalink resolves against the pool at its own commit forever, so the stub need not keep its anchor.
    assert gwt.inbound_pool_anchors(files) == {"branch-anchor", "rel-anchor"}


def _tracked_files_at(commit: str, repo: Path = ROOT) -> dict[str, str]:
    """Every file Git tracks at ``commit`` (any type can link the pool), decoded as the cutover decodes the checkout.

    It reads the commit's own tree, never the working tree. A commit that is not there, or an object that will not
    read, fails the test: nothing is skipped and nothing falls back to the files on disk."""
    listing = subprocess.run(["git", "ls-tree", "-r", "-z", "--full-tree", commit], cwd=repo, check=True, capture_output=True).stdout
    blobs: dict[str, str] = {}
    for entry in filter(None, listing.split(b"\0")):
        meta, _, path = entry.partition(b"\t")
        _mode, kind, sha = meta.decode("ascii").split()
        if kind == "blob":  # a submodule entry is a commit, not a readable file
            blobs[path.decode("utf-8")] = sha
    stream = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        check=True,
        capture_output=True,
        input="".join(f"{sha}\n" for sha in blobs.values()).encode("ascii"),
    ).stdout
    files, position = {}, 0
    for path, sha in blobs.items():
        end = stream.index(b"\n", position)
        header = stream[position:end].split()
        if len(header) != 3 or header[0].decode("ascii") != sha or header[1] != b"blob":
            raise RuntimeError(f"{path} at {commit}: object {sha} did not read ({stream[position:end].decode('ascii', 'replace')})")
        size = int(header[2])
        files[path] = stream[end + 1 : end + 1 + size].decode("utf-8", "replace")
        position = end + 1 + size + 1  # the object's bytes, then one newline
    if position != len(stream):
        raise RuntimeError(f"{commit}: {len(stream) - position} unread bytes after the last object")
    return files


# Plan 11.29 integration (Codex ruling 2026-10-11): this test is about the HISTORICAL baseline, not the current checkout. The
# sealed manifest inventoried the repository at its baseline commit, so its reviewed compat_anchors must cover every pool anchor
# linked from the files at THAT commit. Links other lanes add after the baseline do not belong to the sealed inventory; the cutover
# meets them on the live tree and refuses an unreviewed anchor or a moved pool (render_pool_stub, cutover_docs and their tests above).


def test_every_inbound_pool_link_in_the_baseline_tree_is_a_reviewed_anchor() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    files = {path: text for path, text in _tracked_files_at(inventory.baseline_commit).items() if path != gwt.POOL_PATH}
    found = gwt.inbound_pool_anchors(files)
    assert found, "the baseline tree links no pool anchor: the scan read nothing, so it proves nothing"
    assert found <= set(inventory.compat_anchors)  # what cutover-docs would require of the stub, for the inventoried tree


def test_the_baseline_tree_reader_reads_the_commit_and_never_the_checkout(tmp_path: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=tmp_path, check=True, capture_output=True
        )

    git("init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "kept.md").write_text(f"[old]({gwt.POOL_FILE}#at-the-baseline)\n", encoding="utf-8")
    (tmp_path / "blob.bin").write_bytes(b"\xff\xfe binary \x00 bytes")
    git("add", "-A")
    git("commit", "-q", "-m", "baseline")
    baseline = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    # After the baseline: an edit, a staged addition and an untracked file, all of which a checkout scan would see.
    (tmp_path / "docs" / "kept.md").write_text(f"[new]({gwt.POOL_FILE}#after-the-baseline)\n", encoding="utf-8")
    (tmp_path / "docs" / "added.md").write_text(f"[new]({gwt.POOL_FILE}#added-later)\n", encoding="utf-8")
    git("add", "docs/added.md")
    (tmp_path / "untracked.md").write_text(f"[new]({gwt.POOL_FILE}#never-tracked)\n", encoding="utf-8")
    files = _tracked_files_at(baseline, tmp_path)
    assert set(files) == {"docs/kept.md", "blob.bin"}  # every file type, only what the commit tracked
    assert gwt.inbound_pool_anchors(files) == {"at-the-baseline"}
    assert files["blob.bin"] == b"\xff\xfe binary \x00 bytes".decode("utf-8", "replace")  # the cutover's decode policy


@pytest.mark.parametrize("commit", ["f" * 40, "not-a-revision"])
def test_the_baseline_tree_reader_fails_on_a_commit_it_cannot_read(commit: str) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        _tracked_files_at(commit)


# ==== Plan 11.29 batch 7 (Codex ruling 2026-10-05, option B): a candidate source owner has no issue to bind to ====

_CANDIDATE_OWNED = ("P11-FU-30", "P11-FU-34", "P11-FU-38", "P11-FU-39", "P11-FU-41")
_BOUND_OWNER = "(bound as the native parent at migration; the native link carries the current one)"


def _real_drafts() -> tuple[gwt.Inventory, dict[str, str]]:
    inventory = gwt.load_inventory(MANIFEST)
    sources = gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths)
    return inventory, {draft.record_id: draft.body for draft in gwt.draft_issues(inventory, sources)}


def _owner_fact(body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith("- **Source owner")]


def test_a_candidate_owned_record_states_its_owner_without_claiming_a_native_binding() -> None:
    inventory, drafts = _real_drafts()
    kinds = {record.id: record.kind for record in inventory.records}
    owned = {r.id: r.parent for r in inventory.records if r.disposition == "migrate" and r.parent and kinds[r.parent] == "candidate"}
    assert set(_CANDIDATE_OWNED) <= set(owned)  # the five batch 7 records, and the pilot P11-FU-40 beside them
    for record_id, owner in owned.items():
        assert _owner_fact(drafts[record_id]) == [
            f"- **Source owner (historical):** `{owner}`. This source ownership does not by itself establish a GitHub parent link."
        ]
        assert _BOUND_OWNER not in drafts[record_id]
    assert {owned[record_id] for record_id in _CANDIDATE_OWNED} == {"P11.26-CAND-1-RESOURCE-LIFETIME", "P11.26-CAND-2-TELEMETRY-CONTRACT"}


def test_every_other_owner_keeps_the_native_binding_wording() -> None:
    inventory, drafts = _real_drafts()
    kinds = {record.id: record.kind for record in inventory.records}
    others = [r for r in inventory.records if r.disposition == "migrate" and r.parent and kinds[r.parent] != "candidate"]
    assert {"P11-FU-20", "P11.25-FU-1", "P12-FU-1", "P11-FU-31", "plan:11.28"} <= {r.id for r in others}
    for record in others:
        assert _owner_fact(drafts[record.id]) == [f"- **Source owner:** `{record.parent}` {_BOUND_OWNER}."]
    for record in inventory.records:  # a record without an owner states none
        if record.disposition == "migrate" and not record.parent and record.id in drafts:  # an external issue has no draft
            assert _owner_fact(drafts[record.id]) == []


def test_the_selection_never_changes_a_candidate_owned_body() -> None:
    inventory = gwt.load_inventory(MANIFEST)
    drafts = gwt.draft_issues(inventory, gwt.read_sources_at(inventory.baseline_commit, inventory.read_paths))
    client = FakeGitHub(_pilot_issues(), _pilot_labels())
    bodies = []
    for selected in (frozenset({"P11-FU-38"}), frozenset({"P11-FU-38", "P11-FU-39", "P11-FU-41"}), frozenset(_CANDIDATE_OWNED)):
        batch = gwt.plan_migration(inventory, drafts, gwt.read_issues(client), gwt.read_labels(client), selected)
        assert not [c for c in batch.conflicts if "P11-FU-38" in c or "P11-FU-39" in c or "P11-FU-41" in c]
        bodies.append(next(op.payload["body"] for op in batch.operations if op.op == "create-issue" and op.target == "P11-FU-38"))
    assert bodies[0] == bodies[1] == bodies[2] and "(historical):** `P11.26-CAND-1-RESOURCE-LIFETIME`" in bodies[0]
