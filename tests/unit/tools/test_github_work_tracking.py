"""Plan 11.29 work-tracking migration: inventory coverage and disposition rules (tools/github_work_tracking.py)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from tools import github_work_tracking as gwt

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


def _sources() -> dict[str, bytes]:
    return {"pool": POOL.encode("utf-8")}


def _unit(source: str, text: str, needle: str) -> str:
    """The unit key of the first line containing ``needle``."""
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line:
            return f"{source}:{number}"
    raise AssertionError(f"fixture has no line containing {needle!r}")


def _good() -> dict[str, Any]:
    u = lambda needle: _unit("pool", POOL, needle)  # noqa: E731 - local fixture shorthand
    record = {
        "aliases": [],
        "parent": None,
        "duplicate_of": None,
        "duplicate_rationale": None,
        "status_conflict_disposition": None,
        "mitigation_outstanding": False,
        "target_issue": None,
        "priority": "MEDIUM",
        "rationale": "source-derived",
    }
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
            dict(record, id="plan:11.23", kind="plan", status="Blocked", disposition="migrate", target_issue=222, units=[u("[Plan 11.23")]),
            dict(record, id="plan:12.1", kind="plan", status="Blocked", disposition="migrate", units=[u("[Plan 12.1")]),
            dict(
                record,
                id="P11-FU-20",
                kind="follow-up",
                status="Partially implemented",
                disposition="migrate",
                target_issue=223,
                parent="plan:11.23",
                units=[u("| `P11-FU-20` | Attach"), u("### P11-FU-20")],
            ),
            dict(
                record,
                id="P11-FU-40",
                kind="follow-up",
                status="Open",
                disposition="migrate",
                target_issue=224,
                units=[u("| `P11-FU-40`"), u("### P11-FU-40")],
            ),
            dict(
                record,
                id="P11.25-FU-1",
                kind="follow-up",
                status="Promoted",
                disposition="migrate",
                parent="plan:12.1",
                units=[u("| `P11.25-FU-1`"), u("### P11.25-FU-1")],
            ),
            dict(
                record,
                id="P12-FU-1",
                kind="follow-up",
                status="Promoted",
                disposition="migrate",
                parent="plan:12.1",
                units=[u("| `P12-FU-1` | Advisory"), u("### P12-FU-1")],
            ),
            dict(record, id="A2A-C1", kind="obligation", status="Open", disposition="migrate", target_issue=225, units=[u("| C1 |")]),
            dict(record, id="A2A-M17", kind="obligation", status="Closed", disposition="history", units=[u("| M17 |")]),
            dict(
                record,
                id="H4-VERIFIER-FOLLOW-UPS",
                kind="follow-up",
                status="Open",
                disposition="migrate",
                units=[u("## Plan 11.26 H4 verifier")],
            ),
        ],
    }


def _validate(tmp_path: Path, data: dict[str, Any], sources: dict[str, bytes] | None = None) -> gwt.CoverageReport:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return gwt.validate_inventory(gwt.load_inventory(path), sources or _sources())


def _records(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {r["id"]: r for r in data["records"]}


def test_good_fixture_inventory_is_complete(tmp_path: Path) -> None:
    report = _validate(tmp_path, _good())
    assert report.problems == ()
    assert report.ok


def test_inventory_covers_all_source_sections(tmp_path: Path) -> None:
    data = _good()
    data["sections"] = [s for s in data["sections"] if s["title"] != "A2A ledger audit obligations"]
    report = _validate(tmp_path, data)
    assert any("A2A ledger audit obligations" in p and "unclassified section" in p for p in report.problems)

    data = _good()
    data["sections"].append({"source": "pool", "title": "Invented section", "classification": "history", "rationale": "x"})
    assert any("Invented section" in p for p in _validate(tmp_path, data).problems)


def test_missing_obligation_fails(tmp_path: Path) -> None:
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "A2A-C1"]
    report = _validate(tmp_path, data)
    assert any("C1" in p and "unclaimed" in p and "Open" in p for p in report.problems)

    # Open work cannot be hidden by classifying its whole section as history.
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "H4-VERIFIER-FOLLOW-UPS"]
    for section in data["sections"]:
        if section["title"].startswith("Plan 11.26 H4"):
            section["classification"] = "history"
    assert any("H4" in p and "unclaimed" in p for p in _validate(tmp_path, data).problems)

    # A record claiming open work as history needs an explicit terminal disposition.
    data = _good()
    _records(data)["P11-FU-40"]["disposition"] = "history"
    assert any("P11-FU-40" in p and "terminal" in p for p in _validate(tmp_path, data).problems)


def test_duplicate_status_conflict_requires_disposition(tmp_path: Path) -> None:
    conflicting = POOL.replace("| `P11-FU-40` | Real Zed containment | Open |", "| `P11-FU-40` | Real Zed containment | Closed |")
    sources = {"pool": conflicting.encode("utf-8")}
    data = _good()
    data["baseline"]["sources"]["pool"]["blob"] = gwt.git_blob_id(conflicting.encode())
    report = _validate(tmp_path, data, sources)
    assert any("P11-FU-40" in p and "conflicting source statuses" in p for p in report.problems)

    _records(data)["P11-FU-40"]["status_conflict_disposition"] = "Entry is authoritative; index row is stale (reviewed)."
    assert _validate(tmp_path, data, sources).problems == ()


def test_plan_item_distinct_acceptance_preserved(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["plan:11.23"]["units"] += records["P11-FU-20"]["units"]
    data["records"] = [r for r in data["records"] if r["id"] != "P11-FU-20"]
    report = _validate(tmp_path, data)
    assert any("plan:11.23" in p and "plan and item" in p for p in report.problems)


def test_many_source_aliases_require_duplicate_rationale(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["P11.25-FU-1"]["units"] += records["P12-FU-1"]["units"]
    data["records"] = [r for r in data["records"] if r["id"] != "P12-FU-1"]
    report = _validate(tmp_path, data)
    assert any("P11.25-FU-1" in p and "duplicate rationale" in p for p in report.problems)

    records["P11.25-FU-1"]["duplicate_rationale"] = "Same carriage obligation filed twice (reviewed)."
    assert _validate(tmp_path, data).problems == ()

    data = _good()
    _records(data)["P12-FU-1"].update(disposition="duplicate", duplicate_of="P11.25-FU-1")
    assert any("P12-FU-1" in p and "duplicate rationale" in p for p in _validate(tmp_path, data).problems)


def test_accepted_risk_with_unfinished_mitigation_not_excluded(tmp_path: Path) -> None:
    data = _good()
    risk_unit = _unit("pool", POOL, "### Plan 11.7 accepted risk")
    data["records"].append(
        {
            "id": "RISK-REDIS-DURABILITY",
            "kind": "risk",
            "status": "Reviewed disposition",
            "disposition": "not-work",
            "units": [risk_unit],
            "aliases": [],
            "parent": None,
            "duplicate_of": None,
            "duplicate_rationale": None,
            "status_conflict_disposition": None,
            "mitigation_outstanding": False,
            "target_issue": None,
            "priority": None,
            "rationale": "operator-accepted limit",
        }
    )
    assert _validate(tmp_path, data).problems == ()

    _records(data)["RISK-REDIS-DURABILITY"]["mitigation_outstanding"] = True
    report = _validate(tmp_path, data)
    assert any("RISK-REDIS-DURABILITY" in p and "mitigation" in p for p in report.problems)


def test_source_bytes_must_match_the_inventory_baseline(tmp_path: Path) -> None:
    changed = {"pool": POOL.replace("Real Zed containment", "Real Zed containment v2").encode("utf-8")}
    report = _validate(tmp_path, _good(), changed)
    assert any("pool" in p and "baseline" in p for p in report.problems)


def test_every_unit_is_claimed_at_most_once(tmp_path: Path) -> None:
    data = _good()
    records = _records(data)
    records["P11-FU-40"]["units"].append(records["A2A-C1"]["units"][0])
    assert any("claimed by more than one record" in p for p in _validate(tmp_path, data).problems)


def test_load_rejects_an_unknown_schema(tmp_path: Path) -> None:
    data = copy.deepcopy(_good())
    data["schema"] = "something-else"
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        gwt.load_inventory(path)


CUSTODY_POOL = """\
## Plan 11.26 reviewed disposition and remediation custody

| Kind | Identity | Severity | Disposition | Owner-to-be |
|---|---|---|---|---|
| Candidate | `P11.26-CAND-1-RESOURCE-LIFETIME` | HIGH | `ACCEPTED_OPEN` | `P11-FEAT-ACP-RUNTIME-HARDENING` |
| Obligation | `P11.26-UNRUN-ZED` | N/A | `UNRUN` | operator |

### Runtime candidates

| Existing identity | Sequence wave |
|---|---|
| `P11.26-CAND-1-RESOURCE-LIFETIME` | lifecycle foundation |
"""


def _custody_inventory(retire: bool) -> dict[str, Any]:
    u = lambda needle: _unit("pool", CUSTODY_POOL, needle)  # noqa: E731 - local fixture shorthand
    base = {
        "aliases": [],
        "parent": None,
        "duplicate_of": None,
        "duplicate_rationale": None,
        "status_conflict_disposition": None,
        "mitigation_outstanding": False,
        "target_issue": None,
        "priority": "HIGH",
        "rationale": "source-derived",
    }
    disposition = "history" if retire else "migrate"
    return {
        "schema": gwt.SCHEMA,
        "baseline": {"commit": "fixture", "sources": {"pool": {"path": "pool.md", "blob": gwt.git_blob_id(CUSTODY_POOL.encode())}}},
        "sections": [
            {
                "source": "pool",
                "title": "Plan 11.26 reviewed disposition and remediation custody",
                "classification": "mixed",
                "rationale": "candidates and obligations",
            }
        ],
        "records": [
            dict(
                base,
                id="P11.26-CAND-1-RESOURCE-LIFETIME",
                kind="candidate",
                status="ACCEPTED_OPEN",
                disposition=disposition,
                units=[u("| Candidate |"), u("| `P11.26-CAND-1-RESOURCE-LIFETIME` | lifecycle")],
            ),
            dict(base, id="P11.26-UNRUN-ZED", kind="obligation", status="UNRUN", disposition=disposition, units=[u("| Obligation |")]),
            dict(base, id="structure:runtime-candidates", kind="structure", status=None, disposition="not-work", units=[u("### Runtime")]),
        ],
    }


def test_accepted_open_and_unrun_dispositions_count_as_unresolved_work(tmp_path: Path) -> None:
    sources = {"pool": CUSTODY_POOL.encode("utf-8")}
    assert _validate(tmp_path, _custody_inventory(retire=False), sources).problems == ()

    report = _validate(tmp_path, _custody_inventory(retire=True), sources)
    assert any("P11.26-CAND-1-RESOURCE-LIFETIME" in p and "terminal" in p for p in report.problems)
    assert any("P11.26-UNRUN-ZED" in p and "terminal" in p for p in report.problems)


def test_short_obligation_codes_are_identities_only_in_the_first_cell() -> None:
    text = """\
## Plan 11.26 reviewed disposition and remediation custody

| Kind | Note | Disposition |
|---|---|---|
| Candidate | includes C15 precision and H3 escaped-child citations | `ACCEPTED_OPEN` |

## A2A ledger audit obligations

| Obligation | Status |
|---|---|
| H12a | Open |
"""
    units = gwt.source_units("pool", text)
    assert [unit.identity for unit in units] == ["Candidate", "H12a"]


def test_frozen_live_owner_mappings_are_not_status_lines() -> None:
    text = (
        "## Frozen approval bytes and live-status authority\n\n"
        "- `docs/superpowers/plans/archive/x.md` — SHA-256 `" + "A" * 64 + "` — Frozen approval bytes — live status is owned by "
        "the consolidated open-work pool. Live owner: Open item `P11-FU-4`.\n"
    )
    (unit,) = gwt.source_units("pool", text)
    assert unit.kind == "frozen-mapping" and unit.identity == "docs/superpowers/plans/archive/x.md"
    assert not unit.unresolved


def test_records_name_a_known_product_and_a_parent_that_is_not_a_cycle(tmp_path: Path) -> None:
    data = _good()
    _records(data)["A2A-C1"]["product"] = "evidence-a2a"
    assert _validate(tmp_path, data).problems == ()

    _records(data)["A2A-C1"]["product"] = "somewhere-else"
    assert any("A2A-C1" in p and "product" in p for p in _validate(tmp_path, data).problems)

    data = _good()
    records = _records(data)
    records["plan:12.1"]["parent"] = "P12-FU-1"  # P12-FU-1's parent is plan:12.1
    assert any("cycle" in p for p in _validate(tmp_path, data).problems)


def test_a_migrating_record_cannot_hang_under_a_retired_parent(tmp_path: Path) -> None:
    data = _good()
    _records(data)["P11-FU-40"]["parent"] = "A2A-M17"  # a history record never becomes an issue
    assert any("P11-FU-40" in p and "parent" in p and "not migrating" in p for p in _validate(tmp_path, data).problems)


def test_sources_are_read_from_a_commit_not_the_working_tree() -> None:
    sources = gwt.read_sources_at("HEAD", {"project": "pyproject.toml"})
    assert sources["project"] == gwt.git_blob_bytes("HEAD", "pyproject.toml")
    assert b"[project]" in sources["project"]


def test_cli_validate_reports_problems_with_a_nonzero_exit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = _good()
    data["records"] = [r for r in data["records"] if r["id"] != "A2A-C1"]
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    assert gwt.main(["validate", str(path)], reader=lambda commit, paths: _sources()) == 1
    assert "unclaimed unit" in capsys.readouterr().out

    path.write_text(json.dumps(_good()), encoding="utf-8")
    assert gwt.main(["validate", str(path)], reader=lambda commit, paths: _sources()) == 0
